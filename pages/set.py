import streamlit as st
import gspread

# 💡 마스터 파일인 app.py 인프라로부터 구글 시트 공통 객체 및 세션 수입
from app import GOOGLE_SHEET_ID, get_gspread_client

st.title("⚙️ 시스템 환경 설정")
st.subheader("📊 4대보험 정책 요율 및 법정최저임금 관리")
st.caption("이 페이지에서 수정한 설정값은 구글 시트의 '설정' 탭에 양방향 동기화되며 시스템 전역에 즉시 반영됩니다.")

# 전역 세션 메모리에서 기존 설정 인스턴스 검증
if "settings" not in st.session_state:
    st.warning("⚠️ 메인 홈(app.py) 페이지를 먼저 실행하여 세션 데이터를 적재해 주세요.")
    st.stop()

settings = st.session_state.settings

# 오조작 및 데이터 오염 방지를 위해 트랜잭션 단위로 묶인 Form UI 선언
with st.form("system_setting_form", clear_on_submit=False):
    st.write("### 📜 기준 정책 및 보험 요율 설정")
    
    col1, col2 = st.columns(2)
    
    with col1:
        set_year = st.number_input("기준연도 (YYYY)", value=int(settings.get("기준연도", 2026)), step=1)
        set_min_wage = st.number_input("법정 최저임금 (시급 / 원)", value=int(settings.get("최저임금", 10030)), step=10)
        set_pension = st.number_input("국민연금 요율 (%)", value=float(settings.get("국민연금", 4.5)), format="%.3f", step=0.01)
        set_health = st.number_input("건강보험 요율 (%)", value=float(settings.get("건강보험", 3.545)), format="%.3f", step=0.005)
        
    with col2:
        set_longterm = st.number_input("장기요양보험 환산율 (%)", value=float(settings.get("장기요양_환산율", 12.95)), format="%.3f", step=0.01)
        set_emp_under = st.number_input("고용보험 요율 (65세 미만) (%)", value=float(settings.get("고용_65세미만", 0.9)), format="%.3f", step=0.05)
        set_emp_over = st.number_input("고용보험 요율 (65세 이상) (%)", value=float(settings.get("고용_65세이상", 0.0)), format="%.3f", step=0.05)
    
    st.markdown("---")
    save_setting_btn = st.form_submit_button("💾 변경된 설정값 구글 시트에 최종 동기화")

    if save_setting_btn:
        try:
            gc = get_gspread_client()
            ws = gc.open_by_key(GOOGLE_SHEET_ID).worksheet("설정")
            
            # 💡 [요청사항 반영] 제공해주신 구글 시트 설정 탭의 양식 명칭 및 [항목, 값] 2열 구조와 정확히 매치
            new_setting_rows = [
                ["항목", "값"],
                ["기준연도", set_year],
                ["최저임금", set_min_wage],
                ["국민연금", set_pension],
                ["건강보험", set_health],
                ["장기요양_환산율", set_longterm],
                ["고용_65세미만", set_emp_under],
                ["고용_65세이상", set_emp_over]
            ]
            
            # 시트 전체를 덮어쓰는 트랜잭션 수행
            ws.update(values=new_setting_rows, range_name="A1")
            
            # 업데이트 완료 후 전역 세션 캐시 실시간 갱신
            st.session_state.settings = {row[0]: row[1] for row in new_setting_rows[1:]}
            
            st.success("🎯 정책 요율 및 최저임금 설정이 클라우드 구글 스프레드시트에 성공적으로 동기화되었습니다!")
            st.rerun()
            
        except Exception as e:
            st.error(f"❌ 구글 시트 반영 중 통신 트랜잭션 에러 발생: {e}")
