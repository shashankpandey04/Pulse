/* Firebase Cloud Messaging service worker — handles pushes while the page is
 * closed or backgrounded. The foreground case is handled in-app by
 * components/notification-setup.tsx (onMessage).
 *
 * The config mirrors the NEXT_PUBLIC_FIREBASE_* values in .env.local; these
 * keys are public client identifiers by design (the API key is not a secret).
 */
importScripts("https://www.gstatic.com/firebasejs/13.4.0/firebase-app-compat.js");
importScripts("https://www.gstatic.com/firebasejs/13.4.0/firebase-messaging-compat.js");

firebase.initializeApp({
  apiKey: "AIzaSyAF9PbfF5mpDry42KAEzH6iSWvyiMZw4to",
  authDomain: "pulse-623ba.firebaseapp.com",
  projectId: "pulse-623ba",
  storageBucket: "pulse-623ba.firebasestorage.app",
  messagingSenderId: "87353876824",
  appId: "1:87353876824:web:bd9ecce3543bc1f714052d",
});

const messaging = firebase.messaging();

messaging.onBackgroundMessage((payload) => {
  const data = payload.data || {};
  const title =
    (payload.notification && payload.notification.title) ||
    (data.service_name ? `${data.service_name}: ${data.new_state || "state change"}` : "Pulse");
  const body =
    (payload.notification && payload.notification.body) ||
    (data.old_state && data.new_state
      ? `State changed from ${data.old_state} to ${data.new_state}.`
      : "A monitored service changed state.");

  self.registration.showNotification(title, {
    body,
    tag: data.service_id || "pulse", // one notification per service, replaces older ones
    data,
  });
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const serviceId = event.notification.data && event.notification.data.service_id;
  if (serviceId && clients.openWindow) {
    event.waitUntil(clients.openWindow(`/status`));
  }
});
