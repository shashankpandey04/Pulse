"use client";

/**
 * Firebase Cloud Messaging client (browser only).
 *
 * The browser obtains an FCM registration token (with the VAPID key) after the
 * user grants the Notification permission; the token is then POSTed to our own
 * `/api/devices` route, which forwards it to the Pulse backend — that backend
 * later pushes service state changes to every registered device.
 */

import { getApps, initializeApp, type FirebaseApp } from "firebase/app";
import { getMessaging, isSupported, type Messaging } from "firebase/messaging";

const firebaseConfig = {
  apiKey: process.env.NEXT_PUBLIC_FIREBASE_API_KEY ?? "",
  authDomain: process.env.NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN ?? "",
  projectId: process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID ?? "",
  storageBucket: process.env.NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET ?? "",
  messagingSenderId: process.env.NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID ?? "",
  appId: process.env.NEXT_PUBLIC_FIREBASE_APP_ID ?? "",
};

export function firebaseApp(): FirebaseApp {
  return getApps().length ? getApps()[0]! : initializeApp(firebaseConfig);
}

/** The Messaging handle, or null when unavailable (SSR, unsupported browser, unconfigured env). */
export async function messagingIfSupported(): Promise<Messaging | null> {
  if (typeof window === "undefined") return null;
  if (!firebaseConfig.apiKey || !firebaseConfig.projectId || !firebaseConfig.appId) return null;
  try {
    if (!(await isSupported())) return null;
    return getMessaging(firebaseApp());
  } catch {
    return null;
  }
}

/** Register the background-handler service worker (served from /public). */
export async function ensureServiceWorker(): Promise<ServiceWorkerRegistration> {
  return navigator.serviceWorker.register("/firebase-messaging-sw.js");
}
