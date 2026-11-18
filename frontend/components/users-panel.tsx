"use client";

import { useCallback, useEffect, useState } from "react";
import { apiFetch } from "@/lib/client";
import { UserListResponseSchema, type Role, type UserResponse } from "@/lib/schemas";
import { Notice, PrimaryButton, SecondaryButton, inputClass, labelClass } from "@/components/ui";

const ROLES: Role[] = ["admin", "operator", "subscriber"];

function formatWhen(value: string): string {
  return new Date(value).toLocaleString();
}

export function UsersPanel({ selfUid }: { selfUid: string }) {
  const [search, setSearch] = useState("");
  const [users, setUsers] = useState<UserResponse[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busyUid, setBusyUid] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const query = search ? `?search=${encodeURIComponent(search)}&page_size=100` : "?page_size=100";
      const data = await apiFetch<unknown>(`/api/admin/users${query}`);
      setUsers(UserListResponseSchema.parse(data).users);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load users.");
    }
  }, [search]);

  useEffect(() => {
    void load();
  }, [load]);

  async function mutate(uid: string, path: string, init: RequestInit) {
    setBusyUid(uid);
    setError(null);
    setNotice(null);
    try {
      await apiFetch(path, init);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Action failed.");
    } finally {
      setBusyUid(null);
    }
  }

  return (
    <section className="border border-edge bg-white">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-edge px-4 py-3">
        <h2 className="text-sm font-semibold uppercase tracking-wide">Users</h2>
        <div className="flex items-end gap-2">
          <div>
            <span className={labelClass}>Search email</span>
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="substring…"
              className={`${inputClass} w-56`}
            />
          </div>
        </div>
      </header>
      <div className="p-4">
        {error && <Notice kind="error">{error}</Notice>}
        {notice && <Notice kind="success">{notice}</Notice>}
        <table className="mt-2 w-full text-sm">
          <thead>
            <tr className="border-b border-edge text-left font-mono text-xs uppercase tracking-wide text-muted">
              <th className="py-2 pr-4">Email</th>
              <th className="py-2 pr-4">Role</th>
              <th className="py-2 pr-4">Active</th>
              <th className="py-2 pr-4">Created</th>
              <th className="py-2">Actions</th>
            </tr>
          </thead>
          <tbody>
            {!users && !error && (
              <tr>
                <td colSpan={5} className="py-3 text-muted">
                  Loading…
                </td>
              </tr>
            )}
            {users?.map((user) => {
              const self = user.uid === selfUid;
              return (
                <tr key={user.uid} className="border-b border-edge last:border-b-0">
                  <td className="py-2 pr-4">
                    {user.email}
                    {self && <span className="ml-2 font-mono text-xs text-muted">(you)</span>}
                  </td>
                  <td className="py-2 pr-4">
                    <select
                      value={user.role}
                      disabled={self || busyUid === user.uid}
                      onChange={(e) =>
                        mutate(user.uid, `/api/admin/users/${user.uid}`, {
                          method: "PATCH",
                          body: JSON.stringify({ role: e.target.value }),
                        })
                      }
                      className={`${inputClass} w-36`}
                    >
                      {ROLES.map((role) => (
                        <option key={role} value={role}>
                          {role}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td className="py-2 pr-4 font-mono text-xs">{user.active ? "yes" : "no"}</td>
                  <td className="py-2 pr-4 font-mono text-xs">{formatWhen(user.created_at)}</td>
                  <td className="py-2">
                    {self ? (
                      <span className="font-mono text-xs text-muted">—</span>
                    ) : (
                      <div className="flex gap-2">
                        <SecondaryButton
                          type="button"
                          disabled={busyUid === user.uid}
                          onClick={() =>
                            mutate(user.uid, `/api/admin/users/${user.uid}`, {
                              method: "PATCH",
                              body: JSON.stringify({ active: !user.active }),
                            })
                          }
                        >
                          {user.active ? "Deactivate" : "Reactivate"}
                        </SecondaryButton>
                        {user.active && (
                          <PrimaryButton
                            type="button"
                            disabled={busyUid === user.uid}
                            onClick={() => {
                              if (confirm(`Deactivate ${user.email}? The account can no longer sign in.`)) {
                                void mutate(user.uid, `/api/admin/users/${user.uid}`, { method: "DELETE" });
                              }
                            }}
                          >
                            Delete
                          </PrimaryButton>
                        )}
                      </div>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        <p className="mt-3 font-mono text-xs text-muted">
          Delete = soft delete (deactivated, history preserved). You cannot change your own role or deactivate yourself.
        </p>
      </div>
    </section>
  );
}
