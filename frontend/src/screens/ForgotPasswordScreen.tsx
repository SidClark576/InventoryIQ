import { useEffect, useState } from "react";
import { Link } from "react-router";
import { AUTH_ENDPOINT } from "@/config";
import { TEXT_LINK_CLASS } from "@/components/text-link";
import { Alert, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

type MsgKind = "err" | "info" | "ok";

type StatusMsg = {
  kind: MsgKind;
  text: string;
};

const SENT =
  "If that email is registered, a reset link has been sent. Check your inbox.";

export function ForgotPasswordScreen() {
  const [email, setEmail] = useState("");
  const [msg, setMsg] = useState<StatusMsg | null>(null);
  const [sent, setSent] = useState(false);
  const [pending, setPending] = useState(false);

  useEffect(() => {
    document.title = "InventoryIQ | Forgot Password";
  }, []);

  async function handleForgotPassword(event: React.FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    const trimmed = email.trim();
    if (!trimmed) {
      const text = "Enter your email address.";
      setMsg({ kind: "err", text });
      return;
    }
    setPending(true);
    setMsg({ kind: "info", text: "Sending..." });
    try {
      const res = await fetch(`${AUTH_ENDPOINT}/forgot-password`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: trimmed }),
      });
      // Rate limits and server errors mean nothing was sent; say so instead of "sent".
      if (res.status === 429 || res.status >= 500) {
        setMsg({
          kind: "err",
          text: res.status === 429 ? "Too many requests. Wait a minute and try again." : "Couldn't send the link. Try again shortly.",
        });
        return;
      }
      // Every other answer shows the same message, so it can't reveal which emails are registered.
      setMsg({ kind: "ok", text: SENT });
      setSent(true);
    } catch {
      const text = "Network error. Please try again.";
      setMsg({ kind: "err", text });
    } finally {
      setPending(false);
    }
  }

  return (
    <main className="flex min-h-svh items-center justify-center bg-background px-6 py-10">
      <div className="flex w-full max-w-[400px] flex-col gap-6">
        <p className="text-center text-base font-semibold tracking-tight">InventoryIQ</p>
        <Card>
          <CardHeader>
            <CardTitle>Forgot password</CardTitle>
            <CardDescription>Enter your email and we&apos;ll send a reset link.</CardDescription>
          </CardHeader>
          <CardContent>
            <form className="flex flex-col gap-5" onSubmit={(event) => void handleForgotPassword(event)}>
              <div className="flex flex-col gap-2">
                <Label htmlFor="fp-email">Email address</Label>
                <Input
                  id="fp-email"
                  type="email"
                  autoComplete="email"
                  placeholder="name@company.com"
                  value={email}
                  disabled={sent}
                  onChange={(event) => setEmail(event.target.value)}
                />
              </div>
              <Button type="submit" className="w-full" disabled={pending || sent}>
                Send Reset Link
              </Button>
              {msg ? (
                <Alert id="fp-msg" variant={msg.kind === "err" ? "destructive" : "default"}>
                  <AlertTitle>{msg.text}</AlertTitle>
                </Alert>
              ) : null}
              <p className="border-t pt-5 text-center text-sm text-muted-foreground">
                Remember your password?{" "}
                <Link to="/login" className={TEXT_LINK_CLASS}>
                  Log In
                </Link>
              </p>
            </form>
          </CardContent>
        </Card>
      </div>
    </main>
  );
}
