import os
import pathlib
from langchain.chat_models import init_chat_model
from langchain_community.utilities import SQLDatabase
from langchain_community.agent_toolkits import SQLDatabaseToolkit
from langchain.agents import create_agent
from create_db import create_hospital_db

from dotenv import load_dotenv
load_dotenv()


def setup_database(db_path: str):
    """
    데이터베이스 준비

    Args:
        db_path: SQLite 데이터베이스 파일 경로
    """
    local_path = pathlib.Path(db_path)

    if local_path.exists():
        print(f"[OK] 데이터베이스 파일이 이미 존재합니다: {db_path}")
        return

    csv_dir = pathlib.Path("csv_templates")

    if not csv_dir.exists():
        print(f"[ERROR] CSV 템플릿 폴더를 찾을 수 없습니다: {csv_dir}")
        print(f"\n[INFO] 데이터베이스를 생성하는 방법:")
        print(f"   1. create_db.py를 실행: python create_db.py")
        print(f"   2. 또는 csv_templates 폴더를 확인하세요")
        raise FileNotFoundError(f"CSV 템플릿 폴더를 찾을 수 없습니다: {csv_dir}")

    print("[INFO] hospital.db를 CSV 템플릿에서 생성 중...")
    try:
        create_hospital_db(db_path=str(local_path), csv_dir=str(csv_dir))
        print(f"[OK] 데이터베이스 생성 완료: {db_path}")
    except Exception as e:
        print(f"[ERROR] 데이터베이스 생성 실패: {e}")
        raise


def initialize_model(model_name: str):
    return init_chat_model(model_name)


def connect_database(db_path: str):
    """
    데이터베이스 연결

    Args:
        db_path: SQLite 데이터베이스 파일 경로

    Returns:
        SQLDatabase 객체
    """
    return SQLDatabase.from_uri(f"sqlite:///{db_path}")


def setup_tools(db, model):
    """
    SQL 데이터베이스와 상호작용하는 도구들을 준비합니다.

    Toolkit이 제공하는 도구들:
    - sql_db_query: SQL 쿼리 실행
    - sql_db_schema: 테이블 스키마 조회
    - sql_db_list_tables: 테이블 목록 조회
    - sql_db_query_checker: 쿼리 검증
    """
    toolkit = SQLDatabaseToolkit(db=db, llm=model)
    tools = toolkit.get_tools()

    print("\n사용 가능한 도구들:")
    for tool in tools:
        print(f"  - {tool.name}: {tool.description}")

    return tools


def create_sql_agent(model, tools, db):
    system_prompt = """
당신은 SQL 데이터베이스와 대화하는 전문 Agent입니다.

질문을 받으면:
1. 먼저 데이터베이스의 테이블 목록을 확인합니다
2. 관련 테이블의 스키마를 조회합니다
3. 문법적으로 올바른 {dialect} 쿼리를 생성합니다
4. 쿼리를 실행하기 전에 반드시 검증합니다
5. 쿼리를 실행하고 결과를 분석합니다
6. 분석 결과를 기반으로 사용자에게 답변을 제공합니다

중요 규칙:
- 사용자가 특정 개수를 요청하지 않으면 최대 {top_k}개 결과만 반환
- 실행 전 반드시 쿼리를 검증할 것
- 오류 발생 시 쿼리를 수정하고 재시도
- INSERT, UPDATE, DELETE, DROP 등의 DML 문은 절대 사용 금지
- 필요한 컬럼만 조회 (SELECT *는 피할 것)
""".format(
        dialect=db.dialect,
        top_k=5,
    )

    agent = create_agent(
        model,
        tools,
        system_prompt=system_prompt,
    )

    print("\n[OK] SQL Agent 준비 완료!\n")

    return agent


def query_agent(agent, question: str, verbose: bool = True):
    """
    자연어 질문을 받아서 SQL Agent가 답변합니다.

    Args:
        agent: SQL Agent
        question: 데이터베이스에 대한 질문 (자연어)
        verbose: 상세 로그 출력 여부

    Returns:
        Agent의 최종 답변
    """
    print(f"[INFO] 질문: {question}\n")
    print("[INFO] Agent 실행 중...\n")
    print("-" * 60)

    # Agent 실행 (스트리밍 방식)
    for step in agent.stream(
        {"messages": [{"role": "user", "content": question}]},
        stream_mode="values",
    ):
        # 각 단계의 마지막 메시지 출력
        if verbose:
            step["messages"][-1].pretty_print()

    print("-" * 60)

    # 최종 답변 반환
    final_message = step["messages"][-1]
    return final_message.content


def get_database_info(db):
    print("\n[INFO] 데이터베이스 정보")
    print(f"  - 타입: {db.dialect}")
    print(f"  - 테이블: {', '.join(db.get_usable_table_names())}")

    # 샘플 데이터 조회 (테이블이 있는 경우만)
    tables = db.get_usable_table_names()
    if tables:
        first_table = tables[0]
        print(f"\n샘플 데이터 ({first_table} 테이블):")
        try:
            result = db.run(f"SELECT * FROM {first_table} LIMIT 5;")
            print(f"  {result}")
        except Exception as e:
            print(f"  (샘플 조회 실패: {e})")


def initialize_sql_agent(db_path: str = "hospital.db", model_name: str = "anthropic:claude-sonnet-4-6"):
    """
    SQL Agent 초기화 (모든 단계를 통합한 헬퍼 함수)

    Args:
        db_path: SQLite 데이터베이스 파일 경로 (기본값: hospital.db)
        model_name: 사용할 LLM 모델 이름 (기본값: anthropic:claude-sonnet-4-6)

    Returns:
        (agent, db, model, tools) 튜플
    """
    # 1단계: 데이터베이스 준비
    setup_database(db_path)

    # 2단계: LLM 모델 초기화
    model = initialize_model(model_name)

    # 3단계: 데이터베이스 연결
    db = connect_database(db_path)

    # 4단계: SQL 도구 준비
    tools = setup_tools(db, model)

    # 5단계: Agent 생성
    agent = create_sql_agent(model, tools, db)

    return agent, db, model, tools


def main():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return

    print("\n[INFO] SQL Agent 테스트\n")

    # SQL Agent 초기화
    agent, db, model, tools = initialize_sql_agent(model_name="anthropic:claude-sonnet-4-6")

    # 데이터베이스 정보 출력
    get_database_info(db)

    print("\n" + "=" * 60)
    print("[INFO] 질문을 입력하세요 ('exit' 또는 'quit'로 종료)")
    print("=" * 60 + "\n")
    print("예시 질문:")
    print("  - 데이터베이스에 어떤 테이블들이 있나요?")
    print("  - 환자는 총 몇 명인가요?")
    print("  - 2026년 5월에 응급실에 온 환자는 몇 명인가요?")

    while True:
        try:
            question = input("\n질문: ").strip()

            if question.lower() in ['exit', 'quit', '종료']:
                print("\n👋 SQL Agent를 종료합니다.")
                break

            if not question:
                continue

            query_agent(agent, question)

        except KeyboardInterrupt:
            print("\n\n👋 SQL Agent를 종료합니다.")
            break
        except Exception as e:
            print(f"\n오류 발생: {e}")


if __name__ == "__main__":
    main()
