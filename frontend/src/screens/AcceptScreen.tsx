import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router";
import { toast } from "sonner";
import { acceptInvite } from "@/api";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { getSessionToken, setCurrentOrg, setCurrentRole, setInviteToken } from "@/session";
import { HOME_ROUTE } from "@/app/routes";

const acceptInflight = new Map<string, Promise<Record<string, unknown>>>();

function acceptOnce(token: string): Promise<Record<string, unknown>> {
  const existing = acceptInflight.get(token);
  if (existing) return existing;
  const pending = acceptInvite(token).catch((err: unknown) => {
    acceptInflight.delete(token);
    throw err;
  });
  acceptInflight.set(token, pending);
  return pending;
}

export function AcceptScreen() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const token = searchParams.get("token") || "";
  const [message, setMessage] = useState("Checking invite…");

  useEffect(() => {
    document.title = "InventoryIQ | Accept invite";
  }, []);

  useEffect(() => {
    let active = true;
    if (!getSessionToken()) {
      setInviteToken(token);
      navigate("/login", { replace: true });
      return;
    }
    if (!token) {
      setMessage("Missing invite token.");
      return;
    }
    setMessage("Checking invite…");
    void acceptOnce(token)
      .then((data) => {
        if (!active) return;
        if (data.orgID) {
          setCurrentOrg(String(data.orgID));
          if (data.role) setCurrentRole(String(data.role));
        }
        setMessage("Joined. Redirecting…");
        toast.success("Joined. Redirecting…");
        navigate(HOME_ROUTE, { replace: true });
      })
      .catch((err: unknown) => {
        if (!active) return;
        const text = err instanceof Error && err.message ? err.message : "Could not accept invite.";
        setMessage(text);
        toast.error(text);
      });
    return () => {
      active = false;
    };
  }, [navigate, token]);

  return (
    <main className="flex min-h-svh items-center justify-center bg-background px-6 py-10">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle>Accept invitation</CardTitle>
          <CardDescription id="accept-msg">{message}</CardDescription>
        </CardHeader>
      </Card>
    </main>
  );
}
