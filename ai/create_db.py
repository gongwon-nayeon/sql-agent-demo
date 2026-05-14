import sqlite3
import csv
from pathlib import Path
from typing import Dict, List


def detect_column_type(values: List[str]) -> str:
    """
    실제 데이터 값들을 확인하여 컬럼 타입 결정

    Args:
        values: 컬럼의 모든 데이터 값들

    Returns:
        SQLite 데이터 타입 (TEXT, INTEGER, REAL)
    """
    # 빈 값이 아닌 것들만 확인
    non_empty_values = [v.strip() for v in values if v and v.strip()]

    if not non_empty_values:
        return "TEXT"

    # 모든 값이 정수인지 확인
    all_integers = True
    for v in non_empty_values:
        try:
            # 정수로 변환 가능하고, 앞뒤 0이나 공백 없이 동일한지 확인
            if str(int(v)) != v or '.' in v:
                all_integers = False
                break
        except (ValueError, OverflowError):
            all_integers = False
            break

    if all_integers:
        return "INTEGER"

    # 모든 값이 실수(float)인지 확인
    all_floats = True
    for v in non_empty_values:
        try:
            float(v)
        except (ValueError, OverflowError):
            all_floats = False
            break

    if all_floats:
        return "REAL"

    # 그 외는 모두 TEXT
    return "TEXT"


def detect_primary_key(columns: List[str]) -> str:
    """
    Primary Key 컬럼 감지

    Args:
        columns: 컬럼 리스트

    Returns:
        Primary Key 컬럼명 (없으면 첫 번째 컬럼)
    """
    # *_id 형태의 첫 번째 컬럼을 찾음
    for col in columns:
        if col.lower().endswith('_id') or col.lower() == 'id':
            return col

    # 없으면 첫 번째 컬럼
    return columns[0] if columns else None


def detect_foreign_keys(table_name: str, columns: List[str], all_tables: List[str]) -> Dict[str, str]:
    """
    Foreign Key 관계 감지

    Args:
        table_name: 현재 테이블명
        columns: 현재 테이블의 컬럼 리스트
        all_tables: 모든 테이블 이름 리스트

    Returns:
        {컬럼명: 참조 테이블명} 딕셔너리
    """
    foreign_keys = {}

    for col in columns:
        col_lower = col.lower()

        # patient_id, encounter_id 등의 패턴 찾기
        if col_lower.endswith('_id') and col_lower != f"{table_name.lower()}_id":
            # _id 앞부분 추출
            prefix = col_lower.replace('_id', '')

            # 해당하는 테이블 찾기 (복수형도 체크)
            for other_table in all_tables:
                if other_table.lower() == prefix or other_table.lower() == prefix + 's':
                    foreign_keys[col] = other_table
                    break

    return foreign_keys


def create_hospital_db(db_path: str = "hospital.db", csv_dir: str = "csv_templates"):
    """
    CSV 템플릿에서 hospital.db 생성

    CSV 파일의 구조를 자동으로 분석하여:
    - 컬럼 타입 자동 감지 (실제 데이터 분석)
    - Primary Key 자동 감지 (*_id 컬럼)
    - Foreign Key 자동 감지 (다른 테이블명_id 패턴)

    Args:
        db_path: 생성할 DB 파일 경로
        csv_dir: CSV 파일이 있는 디렉토리
    """
    csv_path = Path(csv_dir)

    if not csv_path.exists():
        print(f"[ERROR] {csv_dir} 폴더를 찾을 수 없습니다.")
        return False

    print(f"\n[INFO] CSV 파일에서 '{db_path}' 생성 중...\n")
    print("[INFO] CSV 파일 구조 자동 분석 중...\n")

    # 1단계: 모든 CSV 파일 스캔하여 구조 분석
    csv_files = sorted(csv_path.glob("*.csv"))

    if not csv_files:
        print(f"[ERROR] {csv_dir} 폴더에 CSV 파일이 없습니다.")
        return False

    table_schemas = {}
    all_table_names = [f.stem for f in csv_files]

    for csv_file in csv_files:
        table_name = csv_file.stem

        # CSV 파일 전체 읽기
        with open(csv_file, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            headers = next(reader)
            all_rows = list(reader)

        if not all_rows:
            print(f"  [ERROR] {table_name}: 데이터가 없습니다.")
            continue

        # 컬럼별로 모든 데이터 값 수집
        column_values = {col: [] for col in headers}
        for row in all_rows:
            for i, col_name in enumerate(headers):
                value = row[i] if i < len(row) else ''
                column_values[col_name].append(value)

        # 각 컬럼의 실제 데이터로 타입 결정
        columns = []
        for col_name in headers:
            col_type = detect_column_type(column_values[col_name])
            columns.append((col_name, col_type))

        # Primary Key 감지
        pk_column = detect_primary_key(headers)

        # Foreign Key 감지
        foreign_keys = detect_foreign_keys(table_name, headers, all_table_names)

        table_schemas[table_name] = {
            'columns': columns,
            'primary_key': pk_column,
            'foreign_keys': foreign_keys,
            'csv_file': csv_file,
            'data': all_rows
        }

        print(f"  [INFO] {table_name}: {len(headers)}개 컬럼, {len(all_rows)}개 행")
        print(f"     - Primary Key: {pk_column}")
        if foreign_keys:
            for fk, ref_table in foreign_keys.items():
                print(f"     - Foreign Key: {fk} → {ref_table}")

        # 타입 정보 출력
        type_summary = {}
        for col_name, col_type in columns:
            type_summary[col_type] = type_summary.get(col_type, 0) + 1
        type_str = ", ".join(f"{t}: {c}" for t, c in type_summary.items())
        print(f"     - 타입: {type_str}")

    # 2단계: 데이터베이스 생성
    print(f"\n[INFO] 데이터베이스 생성 중...\n")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 테이블 생성 및 데이터 로드
    for table_name, schema_info in table_schemas.items():
        # 테이블 삭제 (기존 테이블이 있다면)
        cursor.execute(f"DROP TABLE IF EXISTS {table_name}")

        # CREATE TABLE 문 생성
        col_definitions = []
        for col_name, col_type in schema_info['columns']:
            col_def = f"{col_name} {col_type}"

            # Primary Key 추가
            if col_name == schema_info['primary_key']:
                col_def += " PRIMARY KEY"

            col_definitions.append(col_def)

        # Foreign Key 제약조건 추가
        for fk_col, ref_table in schema_info['foreign_keys'].items():
            pk_of_ref = table_schemas.get(ref_table, {}).get('primary_key')
            if pk_of_ref:
                col_definitions.append(f"FOREIGN KEY ({fk_col}) REFERENCES {ref_table}({pk_of_ref})")

        create_sql = f"CREATE TABLE {table_name} ({', '.join(col_definitions)})"
        cursor.execute(create_sql)
        print(f"  [OK] 테이블 생성: {table_name}")

        # CSV 데이터 로드 (이미 읽어둔 데이터 사용)
        data = schema_info['data']
        if data:
            headers = [col[0] for col in schema_info['columns']]
            placeholders = ",".join(["?" for _ in headers])
            insert_sql = f"INSERT INTO {table_name} VALUES ({placeholders})"
            cursor.executemany(insert_sql, data)
            print(f"  [OK] 데이터 삽입: {len(data)}개 행")
        else:
            print(f"  [ERROR] 데이터 없음")

    conn.commit()
    conn.close()

    print(f"\n[OK] 데이터베이스 생성 완료: {db_path}")
    print(f"[INFO] 총 {len(table_schemas)}개 테이블 생성\n")
    return True


if __name__ == "__main__":
    # ai 폴더에서 실행
    create_hospital_db()
