"use client";
import { useEffect } from "react";
import { messaging, getToken, onMessage } from "@/lib/firebase";

export function useFCM() {
  useEffect(() => {
    async function setupFCM() {
      if (typeof window === "undefined" || !messaging) return;

      try {
        const permission = await Notification.requestPermission();
        if (permission === "granted") {
          const registration = await navigator.serviceWorker.register("/firebase-messaging-sw.js");

          const token = await getToken(messaging, {
            vapidKey: process.env.NEXT_PUBLIC_FIREBASE_VAPID_KEY,
            serviceWorkerRegistration: registration,
          });

          console.log("FCM Device Token:", token);

          // TODO: Send this token to your FastAPI backend to store it in a database associated with the user

        } else {
          console.log("Notification permission denied.");
        }
      } catch (error) {
        console.error("Error setting up FCM token:", error);
      }
    }

    setupFCM();

    // Handle foreground messages while the tab is open
    if (messaging) {
      const unsubscribe = onMessage(messaging, (payload) => {
        console.log("Foreground message received:", payload);
        alert(`New Notification: ${payload.notification?.title} - ${payload.notification?.body}`);
      });
      return () => unsubscribe();
    }
  }, []);
}