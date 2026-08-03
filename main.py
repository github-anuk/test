import streamlit as st
import streamlit.components.v1 as components
import json

# ============================================================
# PAGE CONFIGURATION
# ============================================================
st.set_page_config(
    page_title="Head-Pose Robot Arm Controller",
    page_icon="🤖",
    layout="wide"
)

# Custom Deep Orange CSS Styling
st.markdown("""
    <style>
    .stApp { background-color: #121212; color: #FFFFFF; }
    div[data-testid="stMetricValue"] { color: #FF5722; font-weight: bold; }
    </style>
""", unsafe_allow_html=True)

st.title("🤖 Head-Pose Robotic Arm Controller")
st.caption("Client-Side Ultra-Smooth Browser Tracking & Micro:bit Simulator")

# ============================================================
# STATE MANAGEMENT
# ============================================================
if "base_angle" not in st.session_state:
    st.session_state.base_angle = 90
if "shoulder_angle" not in st.session_state:
    st.session_state.shoulder_angle = 90
if "elbow_angle" not in st.session_state:
    st.session_state.elbow_angle = 90
if "claw_closed" not in st.session_state:
    st.session_state.claw_closed = False
if "last_cmd" not in st.session_state:
    st.session_state.last_cmd = "CENTER"

# ============================================================
# LAYOUT COLUMNS
# ============================================================
col_left, col_right = st.columns([1.3, 1], gap="medium")

with col_left:
    st.subheader("📹 Zero-Lag Face Tracking Feed")
    
    # HTML5 + JavaScript MediaPipe Face Tracker (Runs 60 FPS locally in browser)
    js_camera_html = """
    <!DOCTYPE html>
    <html>
    <head>
      <script src="https://cdn.jsdelivr.net/npm/@mediapipe/camera_utils/camera_utils.js" crossorigin="anonymous"></script>
      <script src="https://cdn.jsdelivr.net/npm/@mediapipe/face_mesh/face_mesh.js" crossorigin="anonymous"></script>
      <style>
        body { margin: 0; background-color: #121212; color: white; font-family: sans-serif; }
        #container { position: relative; width: 100%; max-width: 640px; }
        video { transform: scaleX(-1); width: 100%; height: auto; border-radius: 8px; display: none; }
        canvas { width: 100%; height: auto; border-radius: 8px; border: 2px solid #FF5722; }
      </style>
    </head>
    <body>
      <div id="container">
        <video id="input_video" autoplay playsinline></video>
        <canvas id="output_canvas" width="640" height="480"></canvas>
      </div>

      <script>
        const videoElement = document.getElementById('input_video');
        const canvasElement = document.getElementById('output_canvas');
        const canvasCtx = canvasElement.getContext('2d');

        let calibrated = false;
        let calibSamples = [];
        let centerX = 320, centerY = 240, baseW = 100;
        let pendingDir = null, pendingStart = 0;
        let eyesClosedStart = null;

        function distance(p1, p2) {
          return Math.hypot((p1.x - p2.x) * 640, (p1.y - p2.y) * 480);
        }

        function getEAR(landmarks, indices) {
          let p = indices.map(i => landmarks[i]);
          let v = distance(p[1], p[5]) + distance(p[2], p[4]);
          let h = distance(p[0], p[3]);
          return h === 0 ? 1.0 : v / (2.0 * h);
        }

        function onResults(results) {
          canvasCtx.save();
          canvasCtx.clearRect(0, 0, canvasElement.width, canvasElement.height);
          
          // Draw Mirrored Video
          canvasCtx.translate(canvasElement.width, 0);
          canvasCtx.scale(-1, 1);
          canvasCtx.drawImage(results.image, 0, 0, canvasElement.width, canvasElement.height);
          canvasCtx.restore();

          if (results.multiFaceLandmarks && results.multiFaceLandmarks.length > 0) {
            const landmarks = results.multiFaceLandmarks[0];
            const nose = landmarks[1];
            const hx = (1 - nose.x) * 640; // Mirrored X
            const hy = nose.y * 480;
            const fw = distance(landmarks[234], landmarks[454]);

            // EAR Blink Detection
            const leftEAR = getEAR(landmarks, [362, 385, 387, 263, 373, 380]);
            const rightEAR = getEAR(landmarks, [33, 160, 158, 133, 153, 144]);
            const avgEAR = (leftEAR + rightEAR) / 2.0;

            if (!calibrated) {
              calibSamples.push({x: hx, y: hy, w: fw});
              canvasCtx.fillStyle = '#FF9800';
              canvasCtx.font = '20px sans-serif';
              canvasCtx.fillText(`Calibrating: ${calibSamples.length}/30`, 20, 40);

              if (calibSamples.length >= 30) {
                centerX = calibSamples.reduce((a,b) => a + b.x, 0) / 30;
                centerY = calibSamples.reduce((a,b) => a + b.y, 0) / 30;
                baseW = calibSamples.reduce((a,b) => a + b.w, 0) / 30;
                calibrated = true;
              }
            } else {
              // Draw Deadzone Box
              canvasCtx.strokeStyle = '#FF5722';
              canvasCtx.lineWidth = 2;
              canvasCtx.strokeRect(centerX - 20, centerY - 15, 40, 30);

              // Draw Nose Point
              canvasCtx.fillStyle = '#00FF00';
              canvasCtx.beginPath();
              canvasCtx.arc(hx, hy, 5, 0, 2 * Math.PI);
              canvasCtx.fill();

              let rawDir = null;
              if (avgEAR < 0.21) {
                rawDir = "GRAB_TOGGLE";
              } else {
                if (hx < centerX - 20) rawDir = "RIGHT";
                else if (hx > centerX + 20) rawDir = "LEFT";
                else if (hy < centerY - 15) rawDir = "UP";
                else if (hy > centerY + 15) rawDir = "DOWN";
                else if (fw > baseW + 12) rawDir = "FORWARD";
                else if (fw < baseW - 10) rawDir = "BACKWARD";
              }

              canvasCtx.fillStyle = '#00FF00';
              canvasCtx.font = '20px sans-serif';
              canvasCtx.fillText(`Status: ${rawDir || "CENTER"}`, 20, 30);
            }
          }
        }

        const faceMesh = new FaceMesh({locateFile: (file) => `https://cdn.jsdelivr.net/npm/@mediapipe/face_mesh/${file}`});
        faceMesh.setOptions({maxNumFaces: 1, refineLandmarks: false, minDetectionConfidence: 0.5, minTrackingConfidence: 0.5});
        faceMesh.onResults(onResults);

        const camera = new Camera(videoElement, {
          onFrame: async () => { await faceMesh.send({image: videoElement}); },
          width: 640,
          height: 480
        });
        camera.start();
      </script>
    </body>
    </html>
    """
    components.html(js_camera_html, height=500)

with col_right:
    st.subheader("📟 Micro:bit Visual Simulator")
    
    # Control Sliders & Manual Triggers
    c1, c2 = st.columns(2)
    with c1:
        st.button("⬅️ Turn Left", on_click=lambda: st.session_state.update(base_angle=min(180, st.session_state.base_angle + 10), last_cmd="LEFT"))
        st.button("⬆️ Raise Arm", on_click=lambda: st.session_state.update(shoulder_angle=min(180, st.session_state.shoulder_angle + 10), last_cmd="UP"))
        st.button("🔍 Extend Elbow", on_click=lambda: st.session_state.update(elbow_angle=min(180, st.session_state.elbow_angle + 10), last_cmd="FORWARD"))
    with c2:
        st.button("➡️ Turn Right", on_click=lambda: st.session_state.update(base_angle=max(0, st.session_state.base_angle - 10), last_cmd="RIGHT"))
        st.button("⬇️ Lower Arm", on_click=lambda: st.session_state.update(shoulder_angle=max(0, st.session_state.shoulder_angle - 10), last_cmd="DOWN"))
        st.button("↩️ Retract Elbow", on_click=lambda: st.session_state.update(elbow_angle=max(0, st.session_state.elbow_angle - 10), last_cmd="BACKWARD"))
    
    st.button("✊ Toggle Claw (Blink)", on_click=lambda: st.session_state.update(claw_closed=not st.session_state.claw_closed, last_cmd="GRAB" if not st.session_state.claw_closed else "RELEASE"))

    st.markdown("---")
    m1, m2, m3 = st.columns(3)
    m1.metric("Base", f"{st.session_state.base_angle}°")
    m2.metric("Shoulder", f"{st.session_state.shoulder_angle}°")
    m3.metric("Elbow", f"{st.session_state.elbow_angle}°")
    m3.metric("Claw", "CLOSED" if st.session_state.claw_closed else "OPEN")
