#!/bin/bash
echo -e "\033[1;36m======================================================\033[0m"
echo -e "\033[1;36m      ESP32 Captive Portal Bypass (MAC Spoofing)      \033[0m"
echo -e "\033[1;36m======================================================\033[0m"
echo "This script will temporarily disguise your Mac as your"
echo "ESP32 so you can log into the University Google page."
echo ""

# Find the Wi-Fi interface (usually en0)
WIFI_IF=$(networksetup -listallhardwareports | awk '/Wi-Fi|AirPort/{getline; print $NF}')
if [ -z "$WIFI_IF" ]; then
    WIFI_IF="en0"
fi

# Save original MAC
ORIG_MAC=$(ifconfig $WIFI_IF | grep ether | awk '{print $2}')
echo -e "Your Mac's original MAC address is: \033[1;33m$ORIG_MAC\033[0m"
echo ""

echo "Please enter your ESP32's MAC address (e.g., A4:CF:12:34:56:78):"
read ESP32_MAC

if [ -z "$ESP32_MAC" ]; then
    echo -e "\033[1;31mNo MAC entered. Exiting.\033[0m"
    exit 1
fi

echo ""
echo "We need Administrator privileges to safely change your MAC address."
echo "Disconnecting Wi-Fi..."
networksetup -setairportpower $WIFI_IF off
sleep 1

echo "Spoofing Mac to look like ESP32 ($ESP32_MAC)..."
sudo ifconfig $WIFI_IF ether $ESP32_MAC

echo "Reconnecting Wi-Fi..."
networksetup -setairportpower $WIFI_IF on
sleep 3

echo ""
echo -e "\033[1;32m======================================================\033[0m"
echo -e "\033[1;32m                 ACTION REQUIRED                      \033[0m"
echo -e "\033[1;32m======================================================\033[0m"
echo "1. Wait for your Mac to connect to the University Wi-Fi."
echo "2. Open your web browser and log into the Captive Portal."
echo "3. Verify you have full internet access."
echo -e "\033[1;32m======================================================\033[0m"
read -p "Press [Enter] ONLY AFTER you have successfully logged in..."

echo ""
echo "Restoring your Mac's original MAC address ($ORIG_MAC)..."
networksetup -setairportpower $WIFI_IF off
sleep 1
sudo ifconfig $WIFI_IF ether $ORIG_MAC
networksetup -setairportpower $WIFI_IF on

echo ""
echo -e "\033[1;32mDone! Your Mac is back to normal.\033[0m"
echo "You can now turn on your ESP32. It should connect directly to the Uni Wi-Fi!"
echo "Press any key to exit..."
read -n 1
