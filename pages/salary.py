import streamlit as st
import pandas as pd
import math
from datetime import datetime

# 💡 공통 인프라 파일(db_core)로부터 자원 수입
from db_core import GOOGLE_SHEET_ID, get_gspread_client

st.title("⏱️ 근로시간 입력 및 월급 정산 시스템")

# 전역 세션 상태 검증 및 동기화 인스턴스 체크
if "settings" not in st.session_state or "active_emp_df" not in st.session_state:
    st.warning("⚠️ 메인 홈(app.py) 페이지를 먼저 실행하여 전역 세션 데이터를 적재해 주세요.")
    st.stop()

settings = st.session_state.settings
active_emp_df = st.session_state.active_emp_df

# 변수 스코프 사전 확보를 위해 정산월 입력 컴포넌트를 최상단으로 전면 배치
st.markdown("---")
target_month = st.text_input("마감 처리할 정산월 (예: 2026-05)", value=datetime.now().strftime("%Y-%m"))

# 데이터 매핑 오브젝트 팩토리 빌드
USER_MAPPING = {}
if not active_emp_df.empty:
    for _, row in active_emp_df.iterrows():
        c_id = str(row.get("캡스ID", "")).strip()
        if not c_id or c_id == "nan": 
            continue
        USER_MAPPING[c_id] = {
            "emp_no": str(row.get("사원ID", "00-00")), 
            "name": str(row.get("이름", "무명")),
            "birth": str(row.get("생년월일", "1995-01-01")), 
            "pay_type": str(row.get("정산유형", "시급")),
            "base_pay": int(row.get("기본급", 10030)),
            "car_pay": int(row.get("차량지원금", 0)),
            "food_pay": int(row.get("식대지원금", 0)),
            "chk_pension": str(row.get("국민연금", "Y")).strip().upper() == "Y",
            "chk_health": str(row.get("건강보험", "Y")).strip().upper() == "Y",
            "chk_employment": str(row.get("고용보험", "Y")).strip().upper() == "Y"
        }

if not USER_MAPPING:
    st.warning("⚠️ 재직자 명부를 불러오지 못했거나 등록된 캡스 ID가 없습니다.")
    st.stop()

# 전역 마스터 환경 설정 기반 수식 요율 바인딩
r_pension = float(settings.get("국민연금", 4.5)) / 100.0
r_health = float(settings.get("건강보험", 3.545)) / 100.0
r_longterm = float(settings.get("장기요양_환산율", 12.95)) / 100.0
r_under = float(settings.get("고용_65세미만", 0.9)) / 100.0

# =========================================================================
# 1. 캡스 근태 파일 데이터 인입 (파일 업로드 컴포넌트)
# =========================================================================
st.subheader("📥 캡스 근태 파일 업로드")
st.info("💡 캡스 파일이 있다면 업로드 시 자동으로 연산됩니다. 파일이 없어도 즉시 하단에서 수동 정산이 가능합니다.")

f_col1, f_col2 = st.columns(2)
with f_col1: 
    file1 = st.file_uploader("1번 근태 엑셀 파일", type=["xls", "xlsx"])
with f_col2: 
    file2 = st.file_uploader("2번 근태 엑셀 파일", type=["xls", "xlsx"])

# 파일 업로드 즉시 버튼 조작 없이도 '실시간(Live)' 자동 데이터 파싱 연동 구조로 개편
if file1 and file2:
    try:
        df1 = pd.read_excel(file1)
        df2 = pd.read_excel(file2)
        c_df = pd.concat([df1, df2], ignore_index=True)
        c_df = c_df[c_df['출근시간'].notna() & c_df['퇴근시간'].notna()]
        d_col = '일자' if '일자' in c_df.columns else ('날짜' if '날짜' in c_df.columns else '기본날짜')
        
        parsed_list = []
        for idx, r in c_df.iterrows():
            parsed_list.append({
                "일자": str(r[d_col]).strip() if d_col in c_df.columns else f"2026-05-{idx:02d}",
                "캡스ID": str(r['사용자 id']).strip(),
                "출근시간": str(r['출근시간']).strip()[:5],
                "퇴근시간": str(r['퇴근시간']).strip()[:5],
            })
        st.session_state.caps_db = pd.DataFrame(parsed_list)
    except Exception as e: 
        st.error(f"근태 파일 파싱 및 가공 오류: {e}")
else:
    # 💡 [굳이 정산모드 안 눌러도 되도록 보완] 파일이 없으면 안전하게 빈 데이터프레임 구조를 상시 기본값 배정
    if "caps_db" not in st.session_state:
        st.session_state.caps_db = pd.DataFrame(columns=["일자", "캡스ID", "출근시간", "퇴근시간"])

# 💡 실시간 미등록 유령 캡스 ID 탐지 얼럿 가동 (데이터가 있을 때만 자동 발동)
if not st.session_state.caps_db.empty:
    uploaded_caps_ids = set(st.session_state.caps_db["캡스ID"].unique())
    registered_caps_ids = set(USER_MAPPING.keys())
    unregistered_ids = uploaded_caps_ids - registered_caps_ids
    
    if unregistered_ids:
        st.warning(f"🚨 **[경고] 인사 대장 미등록 근로자(캡스ID) 감지 솔루션 가동**")
        st.write(f"업로드된 캡스 파일에 존재하나 구글 시트 명부에 없는 캡스 ID가 총 {len(unregistered_ids)}건 발견되었습니다.")
        st.code(f"누락된 기기 ID 목록: {sorted(list(unregistered_ids))}", language="text")
        st.markdown("---")

# 연산용 메모리 집계 딕셔너리 구조 초기화
calc_summary = {}
for c_id, info in USER_MAPPING.items():
    calc_summary[c_id] = {
        "total_hours": 0.0, "ot1_hours": 0.0, "ot2_hours": 0.0, "night_hours": 0.0, "holiday_hours": 0.0,
        "late_cnt": 0, "early_cnt": 0, "dinner_cnt": 0, "base_worked_days": 0, "detail_list": []
    }

daily_overtime_rows = []

# =========================================================================
# 2. 캡스 원천 데이터 기반 가산 근로 정산 연산 파이프라인
# =========================================================================
if not st.session_state.caps_db.empty:
    for idx, rec in st.session_state.caps_db.iterrows():
        c_id = rec["캡스ID"]
        if c_id not in USER_MAPPING: 
            continue
        try:
            t_start = datetime.strptime(rec["출근시간"], "%H:%M")
            t_end = datetime.strptime(rec["퇴근시간"], "%H:%M")
            
            h = (t_end - t_start).total_seconds() / 3600.0
            
            # 근로기준법 제54조 휴게시간 세분화 규칙 반영
            if 4.0 <= h < 8.0: h -= 0.5
            elif h >= 8.0: h -= 1.0
                
            adj_h = math.floor(max(0, h) * 2) / 2.0
            
            if t_start > datetime.strptime("09:05", "%H:%M"): calc_summary[c_id]["late_cnt"] += 1
            if t_end < datetime.strptime("17:55", "%H:%M"): calc_summary[c_id]["early_cnt"] += 1
            if adj_h > 0: calc_summary[c_id]["base_worked_days"] = calc_summary[c_id].get("base_worked_days", 0) + 1

            ot1 = 0.0; ot2 = 0.0
            limit_17 = datetime.strptime("17:00", "%H:%M")
            limit_18 = datetime.strptime("18:00", "%H:%M")
            
            if t_end > limit_17:
                end_ot1 = min(t_end, limit_18)
                ot1 = max(0.0, (end_ot1 - limit_17).total_seconds() / 3600.0)
            if t_end > limit_18:
                ot2 = max(0.0, (t_end - limit_18).total_seconds() / 3600.0)
            
            f_ot1 = math.floor(ot1 * 2) / 2.0
            f_ot2 = math.floor(ot2 * 2) / 2.0
            
            calc_summary[c_id]["ot1_hours"] += f_ot1
            calc_summary[c_id]["ot2_hours"] += f_ot2
            calc_summary[c_id]["total_hours"] += adj_h
            
            if adj_h > 8.0:
                daily_overtime_rows.append({
                    "idx": idx, "date": rec["일자"], "name": USER_MAPPING[c_id]["name"], 
                    "caps_id": c_id, "hours": adj_h, "key": f"din_{c_id}_{rec['일자']}_{idx}"
                })
        except: 
            continue

if daily_overtime_rows:
    st.markdown("---")
    st.subheader("🍱 야근자 일자별 석식 공제 (8H 초과 대상)")
    g_cols = st.columns(3)
    for i, o_row in enumerate(daily_overtime_rows):
        with g_cols[i % 3]:
            if st.checkbox(f"📅 {o_row['date']} | {o_row['name']} ({o_row['hours']}H)", value=False, key=o_row["key"]):
                target_c_id = o_row["key"].split("_")[1]
                if target_c_id in calc_summary:
                    calc_summary[target_c_id]["total_hours"] = max(0.0, calc_summary[target_c_id]["total_hours"] - 0.5)

# =========================================================================
# 3. 뷰 컴포넌트 (사원 선택 및 세부 타임테이블/수동 입력 처리)
# =========================================================================
st.markdown("---")
st.subheader("🕵️ 사원별 월간 근태 상세 조회 및 시간 수정")

select_options = ["::: 직원을 선택해주세요 :::"] + list(USER_MAPPING.keys())
select_c_id = st.selectbox(
    "정산 대상 직원 선택", 
    select_options, 
    format_func=lambda x: f"👤 {USER_MAPPING[x]['name']} ({x})" if x in USER_MAPPING else x
)

if select_c_id != "::: 직원을 선택해주세요 :::":
    # 💡 데이터프레임이 비어있지 않고 내부 컬럼이 실재할 때만 근태 타임 에디터 활성화
    if "caps_db" in st.session_state and not st.session_state.caps_db.empty and "캡스ID" in st.session_state.caps_db.columns:
        emp_records = st.session_state.caps_db[st.session_state.caps_db["캡스ID"] == select_c_id].copy()
        if not emp_records.empty:
            st.write(f"📋 **{USER_MAPPING[select_c_id]['name']} 사원의 날짜별 출퇴근 기록 내역 (퇴근시간 편집 가능)**")
            edited_df = st.data_editor(
                emp_records,
                column_config={
                    "일자": st.column_config.TextColumn(disabled=True), 
                    "캡스ID": st.column_config.TextColumn(disabled=True)
                },
                hide_index=True, use_container_width=True, key=f"ed_{select_c_id}"
            )
            if st.button(f"🔄 {USER_MAPPING[select_c_id]['name']} 사원 수정 타임 반영"):
                try:
                    master_db = st.session_state.caps_db.copy()
                    for _, edited_row in edited_df.iterrows():
                        target_caps_id = edited_row["캡스ID"]
                        target_date = edited_row["일자"]
                        new_end_time = edited_row["퇴근시간"]
                        mask = (master_db["캡스ID"] == target_caps_id) & (master_db["일자"] == target_date)
                        master_db.loc[mask, "퇴근시간"] = new_end_time
                    st.session_state.caps_db = master_db
                    st.success("🎯 인덱스 유실 없이 근태 원부 수정 반영 완료!")
                    st.rerun()
                except Exception as e:
                    st.error(f"근태 데이터 매핑 수정 중 오류 발생: {e}")

    st.markdown("---")
    st.subheader("✍️ 수당/공제/근태 추가 항목 및 총 근로시간 수동 입력")
    
    manual_entry_rows = []
    for c_id, info in USER_MAPPING.items():
        if c_id == select_c_id:
            c_data = calc_summary.get(c_id, {"total_hours": 0.0, "ot1_hours": 0.0, "ot2_hours": 0.0})
            manual_entry_rows.append({
                "사원ID": info["emp_no"], "이름": info["name"], "캡스ID": c_id,
                "총근로시간(수동수정 가능)": c_data["total_hours"],
                "직무수당": 0, "직책수당": 0, "결근(일수)": 0, "갑근세": 0, "주민세": 0, "기타공제액": 0, "연차사용(개수)": 0
            })
    
    edited_manual_df = st.data_editor(pd.DataFrame(manual_entry_rows), hide_index=True, use_container_width=True, key="manual_payroll_editor")

    # 급여 내부 실정산 연산 엔진 작동
    final_payroll_db = {}
    
    # 💡 [들여쓰기 정밀 교정] 하단 루프 및 수식 블록전체를 제어문 계층 내부로 완전 수납
    for _, m_row in edited_manual_df.iterrows():
        c_id = m_row["캡스ID"]
        if c_id not in USER_MAPPING:
            continue
            
        emp = USER_MAPPING[c_id]
        c_data = calc_summary.get(c_id, {"total_hours": 0.0, "ot1_hours": 0.0, "ot2_hours": 0.0, "night_hours": 0.0, "holiday_hours": 0.0, "late_cnt": 0, "early_cnt": 0, "dinner_cnt": 0})
        final_total_hours = m_row["총근로시간(수동수정 가능)"]
        
        base_calc = emp["base_pay"] if emp["pay_type"] == "월급" else final_total_hours * emp["base_pay"]
        job_pay = int(m_row["직무수당"])
        duty_pay = int(m_row["직책수당"])
        absent_deduct = int(m_row["결근(일수)"]) * int(emp["base_pay"] if emp["pay_type"] == "시급" else (emp["base_pay"]/30))
        
        if emp["pay_type"] == "월급":
            ot1_pay = int(c_data["ot1_hours"] * (emp["base_pay"] / 209) * 1.5)
            ot2_pay = int(c_data["ot2_hours"] * (emp["base_pay"] / 209) * 1.5)
        else:
            ot1_pay = int(c_data["ot1_hours"] * emp["base_pay"] * 1.5)
            ot2_pay = int(c_data["ot2_hours"] * emp["base_pay"] * 1.5)
            
        정산지급액 = base_calc + ot1_pay + ot2_pay + job_pay + duty_pay - absent_deduct
        지급총액 = 정산지급액 + emp["car_pay"] + emp["food_pay"]
        
        과세대상급여 = base_calc + job_pay + duty_pay - absent_deduct
        tax_free_car = min(emp["car_pay"], 200000)
        tax_free_food = min(emp["food_pay"], 200000)
        보수월액 = max(0, 과세대상급여 - tax_free_car - tax_free_food)
        
        ded_p = int(보수월액 * r_pension) if emp["chk_pension"] else 0
        ded_h = int(보수월액 * r_health) if emp["chk_health"] else 0
        ded_l = int(ded_h * r_longterm) if emp["chk_health"] else 0
        ded_e = int(보수월액 * r_under) if emp["chk_employment"] else 0
        
        gab_tax = int(m_row["갑근세"])
        jum_tax = int(m_row["주민세"])
        etc_ded = int(m_row["기타공제액"])
        
        공제총액 = ded_p + ded_h + ded_l + ded_e + gab_tax + jum_tax + etc_ded
        실수령액 = 지급총액 - 공제총액
        
        final_payroll_db[emp["emp_no"]] = {
            "emp": emp, 
            "c_data": c_data, 
            "m_row": m_row, 
            "final_hours": final_total_hours,
            "pay": {"기본급": base_calc, "연장근로1": ot1_pay, "연장근로2": ot2_pay, "직무수당": job_pay, "직책수당": duty_pay, "차량지원금": emp["car_pay"], "식대지원금": emp["food_pay"], "결근": absent_deduct, "정산지급액": 정산지급액, "지급총액": 지급총액},
            "ded": {"갑근세": gab_tax, "주민세": jum_tax, "국민연금": ded_p, "고용보험": ded_e, "요양보험": ded_h + ded_l, "기타공제액": etc_ded, "공제총액": 공제총액},
            "실수령": 실수령액
        }
