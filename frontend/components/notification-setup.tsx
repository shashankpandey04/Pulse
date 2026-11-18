"use client";

/**
 * Push-notification subscription panel (Firebase Cloud Messaging).
 *
 * Flow: request the Notification permission -> register the FCM service worker
 * -> get the registration token (VAPID key) -> POST it to our own /api/devices
 * (which stores it against the signed-in account). Devices can be removed
 * individually. Foreground messages are surfaced as a line in this panel;
 * background ones are handled by /firebase-messaging-sw.js.
 *
 * Subscription is optional for subscribers; operators and admins must keep at
 * least one device (`required`), so the panel stays pinned until they do.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { apiFetch } from "@/lib/client";
import { DeviceTokenListSchema, type DeviceToken } from "@/lib/schemas";
import { Notice, PrimaryButton, SecondaryButton } from "@/components/ui";

type Props = { required: boolean };

const CURRENT_DEVICE_KEY = "pulse_device_token_id";

function formatWhen(value: string | null): string {
  return value ? new Date(value).toLocaleString() : "—";
}

export function NotificationSetup({ required }: Props) {
  const [devices, setDevices] = useState<DeviceToken[] | null>(null);
  const [permission, setPermission] = useState<NotificationPermission | "unsupported">("default");
  const [currentTokenId, setCurrentTokenId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastMessage, setLastMessage] = useState<string | null>(null);
  const foregroundBound = useRef(false);

  const load = useCallback(async () => {
    try {
      const data = await apiFetch<unknown>("/api/devices");
      setDevices(DeviceTokenListSchema.parse(data).tokens);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load devices.");
    }
  }, []);

  useEffect(() => {
    if (typeof Notification !== "undefined") {
      setPermission(Notification.permission);
    } else {
      setPermission("unsupported");
    }
    const stored = sessionStorage.getItem(CURRENT_DEVICE_KEY);
    if (stored) setCurrentTokenId(stored);
    void load();
  }, [load]);

  /** Foreground messages (page open): show them as an in-panel line. */
  useEffect(() => {
    if (foregroundBound.current) return;
    foregroundBound.current = true;
    void (async () => {
      const { messagingIfSupported } = await import("@/lib/firebase");
      const { onMessage } = await import("firebase/messaging");
      const messaging = await messagingIfSupported();
      if (!messaging) return;
      onMessage(messaging, (payload) => {
        const data = payload.data ?? {};
        const text =
          payload.notification?.title ??
          (data.service_name ? `${data.service_name}: ${data.old_state} → ${data.new_state}` : "State change");
        setLastMessage(text);
        void load(); // send stats may have changed
      });
    })();
  }, [load]);

  async function subscribe() {
    setBusy(true);
    setError(null);
    try {
      const permissionResult = await Notification.requestPermission();
      setPermission(permissionResult);
      if (permissionResult !== "granted") {
        setError("Notification permission was not granted — subscriptions need it to deliver pushes.");
        return;
      }
      const { messagingIfSupported, ensureServiceWorker } = await import("@/lib/firebase");
      const { getToken } = await import("firebase/messaging");
      const registration = await ensureServiceWorker();
      const messaging = await messagingIfSupported();
      if (!messaging) {
        setError("This browser does not support push notifications.");
        return;
      }
      const vapidKey = process.env.NEXT_PUBLIC_FIREBASE_VAPID_KEY;
      if (!vapidKey) {
        setError("Push is not configured (missing VAPID key).");
        return;
      }
      const fcmToken = await getToken(messaging, { vapidKey, serviceWorkerRegistration: registration });
      const registered = await apiFetch<{ token_id: string }>("/api/devices", {
        method: "POST",
        body: JSON.stringify({ fcm_token: fcmToken }),
      });
      sessionStorage.setItem(CURRENT_DEVICE_KEY, registered.token_id);
      setCurrentTokenId(registered.token_id);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not subscribe this device.");
    } finally {
      setBusy(false);
    }
  }

  async function unsubscribe(tokenId: string) {
    setBusy(true);
    try {
      await apiFetch(`/api/devices/${tokenId}`, { method: "DELETE" });
      if (currentTokenId === tokenId) {
        sessionStorage.removeItem(CURRENT_DEVICE_KEY);
        setCurrentTokenId(null);
      }
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not remove the device.");
    } finally {
      setBusy(false);
    }
  }

  const subscribed = (devices?.length ?? 0) > 0;
  const missingRequired = required && !subscribed;

  return (
    <section className={`border bg-white ${missingRequired ? "border-black" : "border-edge"}`}>
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-edge px-4 py-3">
        <h2 className="text-sm font-semibold uppercase tracking-wide">
          Push notifications{required ? " — required for staff" : ""}
        </h2>
        <span className="font-mono text-xs text-muted">
          {permission === "granted" ? "permission granted" : permission === "unsupported" ? "not supported here" : `permission: ${permission}`}
        </span>
      </header>
      <div className="flex flex-col gap-3 p-4">
        <p className="text-sm text-muted">
          Get a browser notification whenever a monitored service changes state (healthy → down → recovered, slow,
          flaky). {missingRequired && <strong className="text-black">Operators and admins must keep at least one device subscribed.</strong>}
        </p>

        {error && <Notice kind="error">{error}</Notice>}
        {lastMessage && (
          <Notice kind="success">
            Latest: {lastMessage}
          </Notice>
        )}

        <div className="flex flex-wrap items-center gap-2">
          {!subscribed ? (
            <PrimaryButton type="button" onClick={subscribe} disabled={busy || permission === "unsupported"}>
              {busy ? "Subscribing…" : "Subscribe this device"}
            </PrimaryButton>
          ) : (
            <>
              <span className="font-mono text-xs text-muted">
                {devices!.length} device{devices!.length === 1 ? "" : "s"} subscribed
              </span>
              <SecondaryButton type="button" onClick={subscribe} disabled={busy}>
                {busy ? "Working…" : "Add another device"}
              </SecondaryButton>
            </>
          )}
        </div>

        {devices && devices.length > 0 && (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-edge text-left font-mono text-xs uppercase tracking-wide text-muted">
                <th className="py-2 pr-4">Device</th>
                <th className="py-2 pr-4">Token</th>
                <th className="py-2 pr-4">Subscribed</th>
                <th className="py-2 pr-4">Pushes</th>
                <th className="py-2">Actions</th>
              </tr>
            </thead>
            <tbody>
              {devices.map((device) => (
                <tr key={device.token_id} className="border-b border-edge last:border-b-0">
                  <td className="py-2 pr-4">
                    {device.device_label ?? "Device"}
                    {device.token_id === currentTokenId && (
                      <span className="ml-2 font-mono text-xs text-muted">(this device)</span>
                    )}
                    {device.user_agent && <div className="font-mono text-xs text-muted">{device.user_agent}</div>}
                  </td>
                  <td className="py-2 pr-4 font-mono text-xs">{device.token_preview}</td>
                  <td className="py-2 pr-4 font-mono text-xs">{formatWhen(device.created_at)}</td>
                  <td className="py-2 pr-4 font-mono text-xs">
                    {device.send_count} sent{device.fail_count > 0 ? ` · ${device.fail_count} failed` : ""}
                    {device.last_error && <div className="font-mono text-xs text-muted">{device.last_error}</div>}
                  </td>
                  <td className="py-2">
                    <SecondaryButton type="button" disabled={busy} onClick={() => unsubscribe(device.token_id)}>
                      Unsubscribe
                    </SecondaryButton>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </section>
  );
}
