// Production Cloud Run API URL.
const localDevelopment = ["127.0.0.1", "localhost"].includes(location.hostname);
window.APP_CONFIG = {
  API_BASE_URL: localDevelopment ? "/api" : "https://avatar-api-82762694345.asia-south1.run.app",
  TTS_BASE_URL: localDevelopment ? "/api" : "https://avatar-api-82762694345.asia-south1.run.app",
  FIREBASE: {
    projectId: "sentientia-holobox-beta",
    appId: "1:525849832519:web:b130b29497856f6108d562",
    storageBucket: "sentientia-holobox-beta.firebasestorage.app",
    apiKey: "AIzaSyALPFFNQFkF-AiR5Mt4uaAQ4C-Qrpgfna4",
    authDomain: "sentientia-holobox-beta.firebaseapp.com",
    messagingSenderId: "525849832519"
  }
};
