import streamlit as st

from components.ui import BASE_CSS, inject, md

inject(BASE_CSS + """
.stApp { background: linear-gradient(160deg,#0b2545 0%,#13315c 45%,#eef2f7 45.1%); }
.block-container { max-width: 1040px; }
.sa-portal { background:#fff; border-radius:20px; padding:24px; border:1px solid #dde4ee; min-height:230px;
             box-shadow:0 10px 30px rgba(11,37,69,.12); }
.sa-portal h3 { margin:6px 0 6px; color:#0b2545; font-size:22px; }
""")
md('<div style="color:#fff;margin:26px 0 30px"><div style="font-size:14px;letter-spacing:.12em;color:#9fb6da;'
   'font-weight:700">SKYASSIST 2.0</div><div style="font-size:40px;font-weight:800;line-height:1.1;margin:6px 0">'
   'Connection management, indoor navigation<br>and human-approved assistance</div>'
   '<div style="color:#c9d6ee;font-size:16px">The AI assists. Deterministic code calculates. A human authorises.</div></div>')
c1, c2 = st.columns(2)
with c1:
    md('<div class="sa-portal"><div style="font-size:30px">🧳</div><h3>Passenger portal</h3>'
       '<div class="sa-muted">See your next gate, time left and connection risk, follow step-by-step indoor directions, '
       'and track your assistance request. Mobile-first.</div></div>')
    st.page_link("views/passenger.py", label="Open passenger portal →", icon="🧳", use_container_width=True)
with c2:
    md('<div class="sa-portal"><div style="font-size:30px">🧑‍✈️</div><h3>Airport coordinator portal</h3>'
       '<div class="sa-muted">Live queue of assistance requests ordered by risk, route map, deterministic calculations, '
       'atomic approve/decline, staff and cart assignment, audit history. Desktop-first.</div></div>')
    st.page_link("views/coordinator.py", label="Open coordinator portal →", icon="🧑‍✈️", use_container_width=True)
st.caption("All flight, gate and passenger data in this build is synthetic demonstration data. "
           "No live flight data, live positioning or real dispatch system is connected.")
