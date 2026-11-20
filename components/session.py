"""Per-session sign-in for each portal. The Principal kept in st.session_state is only a convenience:
every service call re-checks the role/booking in the backend."""
import streamlit as st

from services.auth_service import AuthError, COORDINATOR, PASSENGER, authenticate

DEMO_NOTE = ("Demonstration sign-in with synthetic accounts — not production identity verification. "
             "Passwords are PBKDF2-hashed and set by environment variables.")


def principal(role):
    return st.session_state.get("principals", {}).get(role)


def sign_out(role):
    st.session_state.setdefault("principals", {}).pop(role, None)


def require_login(role, title, subtitle, demo_rows):
    p = principal(role)
    if p:
        return p
    st.markdown(f'<div class="sa-card" style="max-width:520px;margin:40px auto 10px">'
                f'<div class="sa-label">{"Passenger portal" if role == PASSENGER else "Airport coordinator portal"}</div>'
                f'<div style="font-size:26px;font-weight:800;color:#0b2545;margin:4px 0">{title}</div>'
                f'<div class="sa-muted">{subtitle}</div></div>', unsafe_allow_html=True)
    _, mid, _ = st.columns([1, 2, 1])
    with mid:
        with st.form(f"login_{role}", clear_on_submit=False):
            user = st.text_input("Booking reference" if role == PASSENGER else "Coordinator username",
                                 key=f"u_{role}", placeholder="PNR1A2" if role == PASSENGER else "sarah")
            pw = st.text_input("Password", type="password", key=f"p_{role}")
            ok = st.form_submit_button("Sign in", type="primary", use_container_width=True)
        if ok:
            try:
                st.session_state.setdefault("principals", {})[role] = authenticate(user, pw, role)
                st.rerun()
            except AuthError as e:
                st.error(str(e))
        with st.expander("Demo accounts (synthetic data)"):
            st.caption(DEMO_NOTE)
            for r in demo_rows:
                st.markdown(f"- {r}")
    st.stop()


def nav_link(page, label, icon=None):
    """st.page_link that degrades to nothing when a view is rendered outside the router (unit/UI tests)."""
    try:
        st.page_link(page, label=label, icon=icon)
    except Exception:  # StreamlitPageNotFoundError outside st.navigation
        pass
