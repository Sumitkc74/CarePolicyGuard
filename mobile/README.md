# CarePolicyGuard Mobile (React Native / Expo)

Cross-platform clinical companion application built with **React Native (TypeScript)** and **Expo** for hospital rounds and physician prior-authorization bedside decision support.

---

## Architectural Highlights
* **Zero-Lag Slicing:** Consumes the CarePolicyGuard FastAPI verification engine (`/api/v1/adjudicate`) with sub-2-second turnaround.
* **Character-Grounded Evidence:** Displays letter-by-letter clinical quotes and exact statutory criteria status (`MET`, `NOT_MET`, `INSUFFICIENT_EVIDENCE`).
* **Calibrated Safety Gate (&tau; &ge; 0.85):** Displays immediate abstention badges when patient evidence is missing or ambiguous.
* **Peer-to-Peer Appeal Briefs:** Generates verbal talking points and formal briefs for physician phone calls with Medicare Medical Directors directly from mobile screens.

---

## Project Structure
```
mobile/
├── App.tsx             # Primary 3-Tab Navigator (Note Entry, Determination, Peer Appeal)
├── app.json            # Expo configuration (iOS Bundle ID, Android Package)
├── package.json        # Dependencies (React Native, Expo, Safe Area Context)
├── tsconfig.json       # TypeScript configuration
└── src/
    ├── api.ts          # Strongly typed client for CarePolicyGuard REST backend
    └── types.ts        # TypeScript interfaces matching backend Pydantic schemas
```

---

## Quickstart (Development)

### 1. Prerequisites
Ensure Node.js is installed (`node -v` >= 18).

### 2. Install Dependencies
```bash
cd mobile
npm install
```

### 3. Start Expo Dev Server
```bash
npm start
```
* Press **`a`** to launch on an Android Emulator.
* Press **`i`** to launch on an iOS Simulator.
* Press **`w`** to launch in a Web Browser for instant desktop testing.
* Scan the QR code with the **Expo Go** mobile app on your iPhone or Android phone to run on a physical device over Wi-Fi.

---

## Backend Connectivity
By default, the mobile client connects to `http://10.0.2.2:8000/api/v1` (the default Android emulator loopback). For local testing across physical devices or iOS, change `API_BASE_URL` in `src/api.ts` to your machine's local network IP address (e.g. `http://192.168.1.X:8000/api/v1`).

