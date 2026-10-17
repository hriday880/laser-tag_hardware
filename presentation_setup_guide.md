# LaserTag Mark 5 - Presentation Setup Guide

## 1. Network Preparation
Since the ESP firmware is pre-configured for a specific network, you need to create a Wi-Fi network for it to join.
*   **Action**: Turn on a Mobile Hotspot on your phone (or laptop).
*   **SSID (Network Name)**: `Hriday`
*   **Password**: `12345678`
*   *Note: Ensure your Mac is also connected to this hotspot so the server and ESP are on the same network.*

## 2. Start the Server
The server acts as the authoritative referee and hosts the dashboard.
*   **Action**: Double-click the `run_server.command` file located in the `LaserTag-hardware` folder.
*   **What happens**: A terminal window will open, starting the Python server. It will display a live text-based terminal dashboard.

## 3. Open the Dashboard
*   **Action**: Look at the terminal output from the previous step. It will display a link like `http://<YOUR_IP>:5050/`.
*   **Action**: Open your web browser and go to that link (or just use `http://localhost:5050/`).
*   **What happens**: You will see the Laser Tag Web Dashboard.

## 4. Power Up the ESP32
*   **Action**: Plug the ESP32 into your phone (via OTG) or a power bank to power it on.
*   **What happens**: 
    1. The ESP will connect to the `Hriday` Wi-Fi.
    2. It will use UDP auto-discovery to automatically find your Mac's server on the network.
    3. The ESP's LCD will display "LOBBY" and its LEDs will light up.
    4. The Web Dashboard and Terminal will show "Node P1" as ONLINE.

## 5. Live Demonstration Flow
1.  **Start the Match**: On the Web Dashboard, click the **Start** button.
2.  **Countdown**: The ESP's LCD and buzzer will count down (3.. 2.. 1.. GO!).
3.  **Action**: Use the IR remote to shoot the ESP's IR receiver.
    *   *Enemy buttons (e.g., 5-9)* will reduce HP, blink the red LED, and play a hit sound.
    *   *Friend buttons (e.g., 1-4)* act as medics and heal HP.
4.  **Live Updates**: Show the audience how the Web Dashboard and Terminal instantly reflect the HP loss, hits taken, and respawn states.
5.  **Game Over**: Let the ESP lose all its lives to demonstrate the "ELIMINATED" state and the end-of-match melody.
