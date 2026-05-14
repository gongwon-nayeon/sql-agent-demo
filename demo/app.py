import sys
import os
from pathlib import Path
from dotenv import load_dotenv

# ai 폴더를 import path에 추가
ai_dir = Path(__file__).parent.parent / "ai"
sys.path.insert(0, str(ai_dir))

env_path = ai_dir / ".env"
if env_path.exists():
    load_dotenv(env_path)
else:
    print(f".env 파일을 찾을 수 없습니다: {env_path}")

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import json
import asyncio
import re
from sql_agent import initialize_sql_agent # type: ignore
from create_db import create_hospital_db # type: ignore
from langchain.chat_models import init_chat_model

app = FastAPI(title="SQL Agent Demo")


def format_tool_result(result: str, tool_name: str) -> str:
    """도구 결과를 가독성 있게 포맷"""
    if tool_name == "sql_db_schema":
        # CREATE TABLE 구문: 컬럼마다 줄바꿈 + 들여쓰기
        result = re.sub(r"\s*\(\s*", " (\n  ", result)
        result = re.sub(r",\s*([A-Z_])", r",\n  \1", result)
        result = re.sub(r"\s*\)\s*/\*", "\n) /*", result)
        result = re.sub(r"\*/\s*CREATE", "*/\n\nCREATE", result)
        # 샘플 행 설명은 축약
        result = re.sub(r"/\*.*?\*/", lambda m: m.group()[:120] + " */" if len(m.group()) > 120 else m.group(), result, flags=re.DOTALL)
        return result.strip()

    if tool_name in ("sql_db_query", "sql_db_query_checker"):
        # SQL 키워드 앞에 줄바꿈
        keywords = ["SELECT", "FROM", "LEFT JOIN", "RIGHT JOIN", "INNER JOIN", "JOIN",
                    "ON", "WHERE", "GROUP BY", "ORDER BY", "HAVING", "LIMIT", "AND", "OR"]
        for kw in keywords:
            result = re.sub(rf"(?<!\n)\s+{kw}\b", f"\n{kw}", result)
        return result.strip()

    return result

async def generate_related_questions(user_query: str, answer: str) -> list[str]:
    """사용자 질문과 답변을 기반으로 관련 질문 3개를 생성"""
    try:
        llm = init_chat_model(model="anthropic:claude-sonnet-4-6")

        prompt = f"""사용자가 의료 데이터베이스에 대해 다음과 같은 질문을 했고, 답변을 받았습니다:

질문: {user_query}
답변: {answer}

이 대화의 맥락과 관련있는 자연스러운 후속 질문 3개를 생성해주세요.
질문은 짧고 명확하게 작성하고, 각 질문은 새로운 줄에 번호 없이 작성하세요.
각 질문은 한 줄로 작성하고, 20자 이내로 간결하게 만드세요.

예시 형식:
전체 환자 수는?
응급실 방문 통계는?
진료과별 현황은?"""

        response = await asyncio.to_thread(llm.invoke, prompt)

        # 응답을 줄 단위로 분리하고 빈 줄 제거
        questions = [q.strip() for q in response.content.split('\n') if q.strip()]

        # 최대 3개만 반환
        return questions[:3]
    except Exception as e:
        print(f"[ERROR] 관련 질문 생성 실패: {e}")
        # 기본 질문 반환
        return [
            "데이터베이스에는 어떤 테이블이 있나요?",
            "환자 통계를 보여주세요",
            "최근 진료 현황은?"
        ]

app.mount("/static", StaticFiles(directory="static"), name="static")

agent = None
db = None
model = None
tools = None


def initialize_agent():
    global agent, db, model, tools
    if agent is None:
        # API 키 확인
        if not os.getenv("ANTHROPIC_API_KEY"):
            print("\n[ERROR] ANTHROPIC_API_KEY가 설정되지 않았습니다!")
            print("   1. ai/.env 파일을 만들고")
            print("   2. ANTHROPIC_API_KEY=your-key-here 를 입력하세요.\n")
            return False

        ai_dir = Path(__file__).parent.parent / "ai"
        db_path = ai_dir / "hospital.db"
        csv_dir = ai_dir / "csv_templates"

        # DB가 없으면 자동 생성
        if not db_path.exists():
            print("\n[INFO] hospital.db가 없습니다. CSV 템플릿에서 생성합니다...\n")
            if csv_dir.exists():
                create_hospital_db(str(db_path), str(csv_dir))
            else:
                print(f"[ERROR] CSV 템플릿 폴더를 찾을 수 없습니다: {csv_dir}")
                return False

        # Agent 생성 (함수 기반)
        try:
            if db_path.exists():
                agent, db, model, tools = initialize_sql_agent(db_path=str(db_path))
                print("[OK] SQL Agent 초기화 완료!")
                return True
            else:
                return False
        except Exception as e:
            print(f"\n[ERROR] Agent 초기화 실패: {e}\n")
            return False
    return True


@app.get("/")
async def read_root():
    """메인 페이지"""
    return FileResponse("static/index.html")


@app.get("/health")
async def health_check():
    """헬스 체크"""
    db_ready = initialize_agent()
    return {
        "status": "healthy" if db_ready else "no_database",
        "agent_ready": agent is not None
    }


@app.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket):
    """WebSocket 채팅 엔드포인트"""
    await websocket.accept()

    # Agent 초기화
    if not initialize_agent():
        error_msg = "[ERROR] Agent 초기화 실패\n\n"

        if not os.getenv("ANTHROPIC_API_KEY"):
            error_msg += "ANTHROPIC_API_KEY가 설정되지 않았습니다.\n\n"
            error_msg += "해결 방법:\n"
            error_msg += "1. ai/.env 파일 생성\n"
            error_msg += "2. ANTHROPIC_API_KEY=your-key-here 입력\n"
            error_msg += "3. 서버 재시작"
        else:
            error_msg += "데이터베이스 또는 CSV 템플릿을 확인해주세요."

        await websocket.send_json({
            "type": "error",
            "content": error_msg
        })
        await websocket.close()
        return

    try:
        while True:
            # 클라이언트로부터 메시지 수신
            data = await websocket.receive_text()
            message = json.loads(data)

            user_query = message.get("query", "").strip()

            if not user_query:
                continue

            # 사용자 메시지 에코
            await websocket.send_json({
                "type": "user",
                "content": user_query
            })

            # Agent 처리 시작 표시
            await websocket.send_json({
                "type": "thinking",
                "content": "🤔 생각 중..."
            })

            try:
                import queue
                import threading

                final_answer = None

                step_queue = queue.Queue()

                def run_agent_sync():
                    """별도 스레드에서 Agent를 실행하고 각 step을 큐에 넣음"""
                    try:
                        for step in agent.stream(
                            {"messages": [{"role": "user", "content": user_query}]},
                            stream_mode="values",
                        ):
                            step_queue.put(("step", step))
                        step_queue.put(("done", None))
                    except Exception as e:
                        step_queue.put(("error", str(e)))

                agent_thread = threading.Thread(target=run_agent_sync, daemon=True)
                agent_thread.start()

                # 큐에서 step을 가져와서 실시간으로 처리
                while True:
                    try:
                        item_type, item_data = await asyncio.get_event_loop().run_in_executor(
                            None, step_queue.get, True, 0.1
                        )
                    except queue.Empty:
                        continue

                    if item_type == "done":
                        break
                    elif item_type == "error":
                        raise Exception(item_data)
                    elif item_type == "step":
                        step = item_data
                        last_message = step["messages"][-1]

                        # 메시지 타입 확인
                        msg_type = type(last_message).__name__

                        # 1. ToolMessage (도구 실행 결과)
                        if msg_type == 'ToolMessage':
                            tool_name = getattr(last_message, 'name', 'unknown')
                            tool_result = format_tool_result(last_message.content, tool_name)

                            await websocket.send_json({
                                "type": "tool_result",
                                "content": tool_result,
                                "tool_name": tool_name
                            })

                        # 2. AIMessage (AI 응답)
                        elif msg_type == 'AIMessage':
                            # 도구 호출이 있는 경우
                            if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
                                for tool_call in last_message.tool_calls:
                                    tool_name = tool_call.get('name', 'unknown')
                                    tool_args = tool_call.get('args', {})

                                    tool_names_kr = {
                                        'sql_db_list_tables': '테이블 목록 조회',
                                        'sql_db_schema': '테이블 구조 확인',
                                        'sql_db_query_checker': 'SQL 쿼리 검증',
                                        'sql_db_query': 'SQL 쿼리 실행',
                                    }

                                    tool_display = tool_names_kr.get(tool_name, f'도구: {tool_name}')

                                    await websocket.send_json({
                                        "type": "tool_call",
                                        "content": tool_display,
                                        "tool_name": tool_name,
                                        "args": tool_args
                                    })

                            # 도구 호출이 없는 순수 텍스트 답변 (최종 답변!)
                            else:
                                content = last_message.content
                                if content and isinstance(content, str) and content.strip():
                                    final_answer = content.strip()
                                    # 최종 답변 전송
                                    await websocket.send_json({
                                        "type": "assistant",
                                        "content": final_answer
                                    })

                # 관련 질문 생성 및 전송
                if final_answer:
                    related_questions = await generate_related_questions(user_query, final_answer)
                    await websocket.send_json({
                        "type": "suggested_questions",
                        "questions": related_questions
                    })
                else:
                    await websocket.send_json({
                        "type": "error",
                        "content": "응답을 생성하지 못했습니다."
                    })

            except Exception as e:
                await websocket.send_json({
                    "type": "error",
                    "content": f"[ERROR] 오류 발생: {str(e)}"
                })

    except WebSocketDisconnect:
        print("Client disconnected")
    except Exception as e:
        print(f"WebSocket error: {e}")
        try:
            await websocket.send_json({
                "type": "error",
                "content": f"연결 오류: {str(e)}"
            })
        except:
            pass


@app.get("/db/info")
async def get_db_info():
    """데이터베이스 정보 조회"""
    if not initialize_agent():
        return {"error": "Database not found"}

    try:
        info = {
            "dialect": db.dialect,
            "tables": db.get_usable_table_names()
        }
        return {"info": info}
    except Exception as e:
        return {"error": str(e)}


if __name__ == "__main__":
    import uvicorn
    print("[INFO] SQL Agent Demo 서버 시작...")
    print("[INFO] http://localhost:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)
