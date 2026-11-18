importScripts('https://www.gstatic.com/firebasejs/9.22.2/firebase-app-compat.js');
importScripts('https://www.gstatic.com/firebasejs/9.22.2/firebase-messaging-compat.js');

firebase.initializeApp({
  apiKey: "AIzaSyAF9PbfF5mpDry42KAEzH6iSWvyiMZw4to",
  authDomain: "pulse-623ba.firebaseapp.com",
  projectId: "pulse-623ba",
  storageBucket: "pulse-623ba.firebasestorage.app",
  messagingSenderId: "87353876824",
  appId: "1:87353876824:web:bd9ecce3543bc1f714052d"
});

const messaging = firebase.messaging();

messaging.onBackgroundMessage((payload) => {
  console.log('Received background message: ', payload);
  const notificationTitle = payload.notification.title;
  const notificationOptions = {
    body: payload.notification.body,
    icon: '/vercel.svg' // optional
  };

  self.registration.showNotification(notificationTitle, notificationOptions);
});