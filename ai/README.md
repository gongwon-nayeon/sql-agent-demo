# SQL Agent 데이터 커스터마이징

`csv_templates` 폴더의 CSV 파일을 수정하여 자신만의 데이터로 실습할 수 있습니다.

## 방법 1: 기존 데이터 수정

### 1단계: CSV 파일 열기
```
ai/csv_templates/ 폴더로 이동
→ patients.csv, encounters.csv, diagnosis.csv 중 하나를 엑셀로 열기
```

### 2단계: 데이터 수정

**데이터 열/행 추가/수정/삭제:**
```csv
patient_id,sex,birth_date,blood_type,height_cm,weight_kg,smoking,family_history
P001,여,1985-03-12,A,162,55,비흡연,고혈압
P011,남,2000-08-20,B,175,70,비흡연,없음  ← 새 환자 추가!
```

#### 3단계: 데이터베이스 재생성
```bash
cd ai
python create_db.py
```

자동으로 `hospital.db`가 생성되고 업데이트됩니다!

---

### 방법 2: 새로운 테이블 추가

완전히 새로운 테이블을 추가할 수도 있습니다.

#### 1단계: 새 CSV 파일 생성
```
csv_templates/medications.csv 파일 생성
```

#### 2단계: CSV 구조 정의
```csv
medication_id,patient_id,drug_name,dosage,start_date,end_date
M001,P001,아스피린,100mg,2026-05-01,2026-05-31
M002,P002,메트포르민,500mg,2026-04-15,
```

**컬럼명 규칙:**
- `*_id` → 자동으로 TEXT 타입, Primary Key 감지
- `*_date`, `*_time` → TEXT 타입
- `*_cm`, `*_kg`, `age`, `count` → INTEGER 타입
- 숫자 데이터 → 자동으로 INTEGER 또는 REAL 감지
- 나머지 → TEXT 타입

**Foreign Key 자동 감지:**
- `patient_id` → 자동으로 `patients` 테이블 참조
- `encounter_id` → 자동으로 `encounters` 테이블 참조

#### 3단계: 데이터베이스 생성
```bash
python create_db.py
```
