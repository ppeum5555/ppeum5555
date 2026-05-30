import streamlit as st
import pandas as pd
from datetime import datetime

# 공통 인프라 파일(db_core)로부터 자원 수입
from db_core import GOOGLE_SHEET_ID, get_gspread_client, load_employees, clean_amount_columns

st.title("👤 직원 관리 및 인사 명부")

# 1. 전역 세션 메모리 초기 동기화
if "active_emp_df" not in st.session_state or st.session_state.active_emp_df.empty:
    raw_emp = load_employees("재직자리스트", filter_active=True)
    st.session_state.active_emp_df = clean_amount_columns(raw_emp)

active_emp_df = st.session_state.active_emp_df

# 변동 감지 및 현재 선택된 사원 추적용 세션 메모리 바인딩
if "selected_emp_id" not in st.session_state:
    st.session_state.selected_emp_id = "🆕 신규 사원 추가 등록하기"

if "prev_selection" not in st.session_state:
    st.session_state.prev_selection = "🆕 신규 사원 추가 등록하기"

# =========================================================================
# 1. 상단 사원 명부 Grid (클릭 이벤트 연동형 인터랙티브 DataFrame)
# =========================================================================
st.subheader("🏢 현재 전사 재직 사원 명부")
st.caption("💡 아래 명부에서 직원의 행(Row)을 마우스로 클릭하면, 하단 입력 폼에 해당 직원의 정보가 즉시 자동으로 채워집니다.")

# 🆕 신규 등록으로 복귀할 수 있는 안전 밸브 버튼 배치
if st.session_state.selected_emp_id != "🆕 신규 사원 추가 등록하기":
    if st.button("➕ 다시 신규 사원 등록 모드로 전환하기"):
        st.session_state.selected_emp_id = "🆕 신규 사원 추가 등록하기"
        st.rerun()

if not active_emp_df.empty:
    # 💡 [핵심 기능 1] selection_mode를 적용하여 표를 '클릭 제어판'으로 승격
    event_data = st.dataframe(
        active_emp_df, 
        use_container_width=True, 
        hide_index=True,
        on_select="rerun", # 클릭하는 즉시 화면을 리런하여 데이터 전송
        selection_mode="single-row", # 한 줄씩만 선택 가능하도록 제어
        column_config={
            "기본급": st.column_config.NumberColumn("기본급", format="%,d"),
            "차량지원금": st.column_config.NumberColumn("차량지원금", format="%,d"),
            "식대지원금": st.column_config.NumberColumn("식대지원금", format="%,d")
        }
    )
    
    # 사용자가 표에서 특정 행을 클릭했는지 실시간 가로채기(Intercept)
    selected_rows = event_data.get("selection", {}).get("rows", [])
    
    if selected_rows:
        # 클릭된 행의 인덱스를 기반으로 해당 사원의 '사원ID' 도출
        clicked_idx = selected_rows[0]
        chosen_emp_id = active_emp_df.iloc[clicked_idx]["사원ID"]
        
        # 직전 선택과 달라졌을 때만 세션 갱신 및 리런
        if st.session_state.selected_emp_id != chosen_emp_id:
            st.session_state.selected_emp_id = chosen_emp_id
            st.rerun()
else:
    st.info("현재 스프레드시트에 등록된 재직 사원 정보가 없습니다.")
    st.session_state.selected_emp_id = "🆕 신규 사원 추가 등록하기"

# 현재 최종 채택된 사원 ID 바인딩
selected_emp_id = st.session_state.selected_emp_id

# =========================================================================
# 2. 하단 데이터 채우기 팩토리 (모드 전환 분기점)
# =========================================================================
is_edit_mode = selected_emp_id != "🆕 신규 사원 추가 등록하기"

if is_edit_mode:
    target_row = active_emp_df[active_emp_df["사원ID"] == selected_emp_id].iloc[0]
    current_emp_id = str(target_row.get("사원ID", ""))
    init_caps_id = str(target_row.get("캡스ID", ""))
    init_name = str(target_row.get("이름", ""))
    try: init_birth = datetime.strptime(str(target_row.get("생년월일", "1995-01-01")), "%Y-%m-%d")
    except: init_birth = datetime(1995, 1, 1)
    init_nationality = str(target_row.get("국적", "내국인"))
    try: init_hire_date = datetime.strptime(str(target_row.get("입사일", "2026-05-01")), "%Y-%m-%d")
    except: init_hire_date = datetime.now()
    init_pay_type = str(target_row.get("정산유형", "시급"))
    init_base_pay = int(target_row.get("기본급", 10030))
    init_car_pay = int(target_row.get("차량지원금", 0))
    init_food_pay = int(target_row.get("식대지원금", 0))
    init_pension = str(target_row.get("국민연금", "Y")).strip().upper() == "Y"
    init_health = str(target_row.get("건강보험", "Y")).strip().upper() == "Y"
    init_employment = str(target_row.get("고용보험", "Y")).strip().upper() == "Y"
    init_industrial = str(target_row.get("산재보험", "Y")).strip().upper() == "Y"
    
    form_title = f"✏️ {init_name} 사원 인적 정보 정밀 수정 폼 (사원ID: {current_emp_id})"
    btn_label = "💾 위 수정 사항을 클라우드 구글 시트에 실시간 반영"
else:
    hire_date_now = datetime.now()
    hire_prefix = hire_date_now.strftime("%y%m%d")
    try:
        all_emp_df = load_employees("재직자리스트", filter_active=False)
        if not all_emp_df.empty and '사원ID' in all_emp_df.columns:
            same_day_emps = all_emp_df[all_emp_df['사원ID'].astype(str).str.contains(f"^{hire_prefix}-", regex=True)]
            next_number = len(same_day_emps) + 1
        else: next_number = 1
    except: next_number = 1
    
    current_emp_id = f"{hire_prefix}-{next_number:02d}"
    init_caps_id = ""
    init_name = ""
    init_birth = datetime(1995, 1, 1)
    init_nationality = "내국인"
    init_hire_date = datetime.now()
    init_pay_type = "시급"
    init_base_pay = 10030
    init_car_pay = 0
    init_food_pay = 0
    init_pension = True
    init_health = True
    init_employment = True
    init_industrial = True
    
    form_title = f"➕ 신규 사원 인적 자원 생성 폼"
    btn_label = "💾 신규 사원 구글 스프레드시트 최종 저장"

# 공통 저장 처리 트랜잭션 함수 선언
def execute_save_action(emp_id_to_save, c_id, name, birth, nat, hire, p_type, base, car, food, pen, hea, emp_i, ind, is_edit):
    try:
        gc = get_gspread_client()
        ws = gc.open_by_key(GOOGLE_SHEET_ID).worksheet("재직자리스트")
        row_data = [
            emp_id_to_save, c_id.strip(), name.strip(), birth.strftime("%Y-%m-%d"),
            nat.strip(), hire.strftime("%Y-%m-%d"), "", p_type, f"{int(base):,}",
            f"{int(car):,}", f"{int(food):,}", "Y" if pen else "N", "Y" if hea else "N",
            "Y" if emp_i else "N", "Y" if ind else "N"
        ]
        if is_edit:
            all_cells = ws.col_values(1)
            if emp_id_to_save in all_cells:
                row_index = all_cells.index(emp_id_to_save) + 1
                end_col_letter = chr(64 + len(row_data))
                ws.update(values=[row_data], range_name=f"A{row_index}:{end_col_letter}{row_index}")
        else:
            ws.append_row(row_data)
        st.session_state.active_emp_df = pd.DataFrame()
        st.session_state.selected_emp_id = "🆕 신규 사원 추가 등록하기"
    except Exception as e:
        st.error(f"구글 통신 오류: {e}")

# =========================================================================
# 3. 변경 감지 백그라운드 엔진 가동 (인터셉터)
# =========================================================================
if st.session_state.prev_selection != "🆕 신규 사원 추가 등록하기" and selected_emp_id == "🆕 신규 사원 추가 등록하기":
    p_id = st.session_state.prev_selection
    if f"input_name_{p_id}" in st.session_state:
        orig = active_emp_df[active_emp_df["사원ID"] == p_id].iloc[0]
        
        has_changed = (
            st.session_state[f"input_name_{p_id}"] != str(orig.get("이름", "")) or
            st.session_state[f"input_caps_{p_id}"] != str(orig.get("캡스ID", "")) or
            int(st.session_state[f"input_base_{p_id}"]) != int(orig.get("기본급", 10030)) or
            int(st.session_state[f"input_car_{p_id}"]) != int(orig.get("차량지원금", 0)) or
            int(st.session_state[f"input_food_{p_id}"]) != int(orig.get("식대지원금", 0))
        )
        
        if has_changed:
            @st.dialog("⚠️ 수정 중인 데이터 보존 안내")
            def confirm_save_dialog():
                st.warning(f"🚨 현재 편집 중이던 사원({orig.get('이름', '')})의 정보가 수정되었습니다.")
                st.write("작성하신 변경 내용을 구글 시트에 저장한 후 신규 등록으로 이동하시겠습니까?")
                
                c_col1, c_col2 = st.columns(2)
                with c_col1:
                    if st.button("👍 예 (저장 후 신규입력)", use_container_width=True):
                        execute_save_action(
                            p_id, st.session_state[f"input_caps_{p_id}"], st.session_state[f"input_name_{p_id}"],
                            st.session_state[f"input_birth_{p_id}"], st.session_state[f"input_nat_{p_id}"],
                            st.session_state[f"input_hire_{p_id}"], st.session_state[f"input_ptype_{p_id}"],
                            st.session_state[f"input_base_{p_id}"], st.session_state[f"input_car_{p_id}"],
                            st.session_state[f"input_food_{p_id}"], st.session_state[f"input_pen_{p_id}"],
                            st.session_state[f"input_hea_{p_id}"], st.session_state[f"input_emp_{p_id}"],
                            st.session_state[f"input_ind_{p_id}"], True
                        )
                        st.session_state.prev_selection = "🆕 신규 사원 추가 등록하기"
                        st.session_state.selected_emp_id = "🆕 신규 사원 추가 등록하기"
                        st.rerun()
                with c_col2:
                    if st.button("👎 아니오 (저장 없이 신규입력)", use_container_width=True):
                        st.session_state.prev_selection = "🆕 신규 사원 추가 등록하기"
                        st.session_state.selected_emp_id = "🆕 신규 사원 추가 등록하기"
                        st.rerun()
            confirm_save_dialog()

st.session_state.prev_selection = selected_emp_id

# =========================================================================
# 4. 실시간 상태 연동형 입력 폼 마운트 (들여쓰기 완전 교정 완료)
# =========================================================================
st.markdown("---")
with st.form(f"employee_unified_form_{selected_emp_id}", clear_on_submit=False):
    st.write(f"### {form_title}")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        new_name = st.text_input("이름", value=init_name, key=f"input_name_{selected_emp_id}")
        new_caps_id = st.text_input("캡스ID (출퇴근기록 매핑용)", value=init_caps_id, key=f"input_caps_{selected_emp_id}")
        new_birth_date = st.date_input("생년월일 선택", value=init_birth, key=f"input_birth_{selected_emp_id}")
        new_nationality = st.text_input("국적", value=init_nationality, key=f"input_nat_{selected_emp_id}")
        
    with col2:
        form_hire_date = st.date_input("📅 입사일자", value=init_hire_date, key=f"input_hire_{selected_emp_id}")
        pay_types = ["시급", "월급"]
        # 💡 [들여쓰기 교정] col2 내부 종속 위치로 올바르게 수납
        new_pay_type = st.selectbox("정산유형", pay_types, index=pay_types.index(init_pay_type), key=f"input_ptype_{selected_emp_id}")
        new_base_pay = st.number_input("기본급 (원)", min_value=0, value=init_base_pay, format="%d", key=f"input_base_{selected_emp_id}")
        new_car_pay = st.number_input("차량지원금 (원)", min_value=0, value=init_car_pay, format="%d", key=f"input_car_{selected_emp_id}")
        new_food_pay = st.number_input("식대지원금 (원)", min_value=0, value=init_food_pay, format="%d", key=f"input_food_{selected_emp_id}")
        
    with col3:
        st.write("### 📜 4대보험 가입 여부")
        ins_col1, ins_col2 = st.columns(2)
        # 💡 [들여쓰기 교정] 4대보험 가입 여부 체크박스들을 col3 하단 계층으로 배치
        with ins_col1:
            chk_pension = st.checkbox("국민연금", value=init_pension, key=f"input_pension_{selected_emp_id}")
            chk_health = st.checkbox("건강보험", value=init_health, key=f"input_health_{selected_emp_id}")
        with ins_col2:
            chk_employment = st.checkbox("고용보험", value=init_employment, key=f"input_employment_{selected_emp_id}")
            chk_industrial = st.checkbox("산재보험", value=init_industrial, key=f"input_industrial_{selected_emp_id}")
            
    # 💡 [들여쓰기 교정] 양식 마감 제출 버튼을 form 내부 최하단 위치로 안전하게 바인딩
    submit_btn = st.form_submit_button(btn_label)

# 💡 [제어문 정렬] 버튼 클릭 스캔 로직을 폼 외부 표준 계층으로 완벽히 분리
if submit_btn:
    if not new_name.strip() or not new_caps_id.strip():
        st.error("❌ 이름과 캡스ID는 필수 항목입니다.")
    else:
        execute_save_action(
            selected_emp_id if is_edit_mode else current_emp_id,
            new_caps_id, new_name, new_birth_date, new_nationality,
            form_hire_date, new_pay_type, new_base_pay, new_car_pay, new_food_pay,
            chk_pension, chk_health, chk_employment, chk_industrial, is_edit_mode
        )
        st.success("🎯 클라우드 스프레드시트 트랜잭션 반영 완료!")
        st.rerun()
