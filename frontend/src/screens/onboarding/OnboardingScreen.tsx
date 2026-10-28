import { Fragment, useEffect, useRef, useState, type FormEvent, type RefObject } from "react";
import { Navigate, useNavigate } from "react-router";
import { CheckIcon } from "@phosphor-icons/react";
import { toast } from "sonner";
import { addItem, getAllItems, updateOrg, type InventoryItem } from "@/api";
import { HOME_ROUTE } from "@/app/routes";
import { BrandMark } from "@/components/brand-mark";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { errorText } from "@/lib/errors";
import { addInOrder, COUNTRIES, doneText, skipStarterItems, STORE_TYPES } from "@/lib/onboarding";
import { STARTER_ITEMS } from "@/lib/starter-items";
import { cn } from "@/lib/utils";
import { getCurrentOrg, getCurrentRole } from "@/session";

type Step = "store" | "items" | "done";

type StepInfo = { id: Step; label: string };

const STEPS: StepInfo[] = [
  { id: "store", label: "Your store" },
  { id: "items", label: "First items" },
  { id: "done", label: "Done" },
];

const STEPS_WITHOUT_ITEMS = STEPS.filter((s) => s.id !== "items");

function StepIndicator({ step, skipItems }: { step: Step; skipItems: boolean }) {
  const steps = skipItems ? STEPS_WITHOUT_ITEMS : STEPS;
  const current = steps.findIndex((s) => s.id === step);
  return (
    <ol className="flex items-start" aria-label="Setup steps">
      {steps.map((s, idx) => {
        const complete = idx < current;
        const active = idx === current;
        return (
          <Fragment key={s.id}>
            <li className="flex flex-col items-center gap-2" aria-current={active ? "step" : undefined}>
              <span
                className={cn(
                  "flex size-8 items-center justify-center rounded-full border-2 text-xs font-semibold",
                  complete && "border-primary bg-primary text-primary-foreground",
                  active && "border-primary bg-card text-foreground",
                  !complete && !active && "border-border bg-card text-muted-foreground",
                )}
              >
                {complete ? <CheckIcon className="size-4" weight="bold" aria-hidden /> : idx + 1}
              </span>
              <span className={cn("text-xs font-medium whitespace-nowrap", complete || active ? "text-foreground" : "text-muted-foreground")}>
                {s.label}
              </span>
            </li>
            {idx < steps.length - 1 ? (
              <li aria-hidden className={cn("mx-2 mt-4 h-px flex-1", complete ? "bg-primary" : "bg-border")} />
            ) : null}
          </Fragment>
        );
      })}
    </ol>
  );
}

type ItemsStepProps = {
  checked: boolean[];
  setChecked: (update: (prev: boolean[]) => boolean[]) => void;
  busy: boolean;
  progress: string;
  titleRef: RefObject<HTMLDivElement | null>;
  onAdd: () => void;
  onLink: (to: string) => void;
  onSkip: () => void;
};

function ItemsStep({ checked, setChecked, busy, progress, titleRef, onAdd, onLink, onSkip }: ItemsStepProps) {
  const pickedCount = checked.filter(Boolean).length;
  const allPicked = pickedCount === checked.length;
  return (
    <>
      <CardHeader>
        <CardTitle ref={titleRef} tabIndex={-1} className="outline-none">
          Add your first items
        </CardTitle>
        <CardDescription>Start with common items. Quantities and prices start at 0; set them in Stock.</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-5">
        <div className="-mb-3 flex justify-end">
          <Button variant="ghost" size="sm" disabled={busy} onClick={() => setChecked((prev) => prev.map(() => !allPicked))}>
            {allPicked ? "Select none" : "Select all"}
          </Button>
        </div>
        <ul className="flex max-h-[45svh] flex-col overflow-y-auto rounded-lg border border-border">
          {STARTER_ITEMS.map((item, idx) => (
            <li key={item.name} className="border-b border-border last:border-b-0">
              <label className="flex min-h-11 cursor-pointer items-center gap-3 px-3 py-2 text-sm">
                <Checkbox
                  checked={checked[idx] ?? false}
                  onCheckedChange={(next) => setChecked((prev) => prev.map((v, i) => (i === idx ? next === true : v)))}
                />
                <span className="min-w-0 flex-1 truncate">{item.name}</span>
                <span className="text-muted-foreground tabular-nums">{item.description}</span>
              </label>
            </li>
          ))}
        </ul>
        <Button size="lg" disabled={busy || pickedCount === 0} onClick={onAdd} aria-live="polite">
          {busy ? progress : `Add selected (${pickedCount})`}
        </Button>
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="outline" disabled={busy} onClick={() => onLink("/stock?new=1")}>
            Add one myself
          </Button>
          <Button variant="outline" disabled={busy} onClick={() => onLink("/stock?scan=1")}>
            Scan
          </Button>
          <Button variant="outline" disabled={busy} onClick={() => onLink("/stock?import=1")}>
            Import CSV
          </Button>
          <Button variant="ghost" className="ml-auto" disabled={busy} onClick={onSkip}>
            Skip
          </Button>
        </div>
      </CardContent>
    </>
  );
}

const COUNTRY_ITEMS = COUNTRIES.map((c) => ({ value: c.code, label: `${c.label} (${c.currency})` }));

export function OnboardingScreen() {
  const navigate = useNavigate();
  const orgID = getCurrentOrg();
  const [step, setStep] = useState<Step>("store");
  const [name, setName] = useState("");
  const [storeType, setStoreType] = useState("");
  const [country, setCountry] = useState("PH");
  const [checked, setChecked] = useState<boolean[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [added, setAdded] = useState(0);
  const [progress, setProgress] = useState("");
  const titleRef = useRef<HTMLDivElement>(null);
  // Empty while loading; null when the load failed.
  const [existing, setExisting] = useState<InventoryItem[] | null>([]);
  const itemsLoad = useRef<Promise<InventoryItem[] | null>>(Promise.resolve(null));

  useEffect(() => {
    document.title = "Panindo | Set up your store";
  }, []);

  // Stores that already hold stock (migrated users) must not be offered starter items on top of it.
  useEffect(() => {
    itemsLoad.current = getAllItems().catch(() => null);
    void itemsLoad.current.then(setExisting);
  }, []);

  // Move focus to the new step's title so keyboard and screen-reader users aren't left on a removed button.
  useEffect(() => {
    if (step !== "store") titleRef.current?.focus();
  }, [step]);

  // Legacy users without an org (or non-owners) have nothing to set up.
  if (!orgID || getCurrentRole() !== "owner") return <Navigate to={HOME_ROUTE} replace />;

  async function saveStore(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) return setError("Enter your store name.");
    setError("");
    setBusy(true);
    try {
      const currency = COUNTRIES.find((c) => c.code === country)?.currency;
      await updateOrg(orgID, { name: trimmed, storeType: storeType || undefined, country, currency });
      if (skipStarterItems(await itemsLoad.current)) return setStep("done");
      // Starter list fits sari-sari stores; other types start with nothing picked.
      setChecked(STARTER_ITEMS.map(() => storeType === "" || storeType === "sari-sari"));
      setStep("items");
    } catch (err) {
      setError(errorText(err, "Couldn't save your store. Try again."));
    } finally {
      setBusy(false);
    }
  }

  async function addSelected(): Promise<void> {
    const picks = STARTER_ITEMS.filter((_, idx) => checked[idx]);
    setBusy(true);
    const failed = await addInOrder(
      picks,
      (item) => addItem({ ...item, quantity: 0, price: 0 }, crypto.randomUUID()),
      (n) => setProgress(`Adding ${n} of ${picks.length}…`),
    );
    setBusy(false);
    if (failed.length) {
      toast.error(`Couldn't add ${failed.length} of ${picks.length} items`, {
        description: `${failed.map((item) => item.name).join(", ")}. Add them later from Stock.`,
      });
    }
    setAdded(picks.length - failed.length);
    setStep("done");
  }

  return (
    <main className="flex min-h-svh justify-center bg-background px-4 py-10 sm:px-6">
      <div className="flex w-full max-w-[480px] flex-col gap-6">
        <p className="flex items-center justify-center gap-2 text-base font-semibold tracking-tight">
          <BrandMark />
          Panindo
        </p>
        <StepIndicator step={step} skipItems={skipStarterItems(existing)} />
        <Card>
          {step === "store" ? (
            <>
              <CardHeader>
                <CardTitle>Set up your store</CardTitle>
                <CardDescription>Your store name prints at the top of your stock sheet.</CardDescription>
              </CardHeader>
              <CardContent>
                <form className="flex flex-col gap-5" onSubmit={(event) => void saveStore(event)}>
                  <div className="flex flex-col gap-2">
                    <Label htmlFor="store-name">Store name</Label>
                    <Input
                      id="store-name"
                      required
                      maxLength={80}
                      autoComplete="organization"
                      placeholder="e.g. SC3 Sari-Sari Store"
                      value={name}
                      onChange={(event) => setName(event.target.value)}
                    />
                  </div>
                  <div className="flex flex-col gap-2">
                    <Label htmlFor="store-type">Store type (optional)</Label>
                    <Select
                      items={STORE_TYPES.map((t) => ({ value: t.value, label: t.label }))}
                      value={storeType || null}
                      onValueChange={(next) => setStoreType(typeof next === "string" ? next : "")}
                    >
                      <SelectTrigger id="store-type" className="w-full">
                        <SelectValue placeholder="Choose a type" />
                      </SelectTrigger>
                      <SelectContent>
                        {STORE_TYPES.map((t) => (
                          <SelectItem key={t.value} value={t.value}>
                            {t.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="flex flex-col gap-2">
                    <Label htmlFor="store-country">Country</Label>
                    <Select
                      items={COUNTRY_ITEMS}
                      value={country}
                      onValueChange={(next) => {
                        if (typeof next === "string") setCountry(next);
                      }}
                    >
                      <SelectTrigger id="store-country" className="w-full">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {COUNTRY_ITEMS.map((c) => (
                          <SelectItem key={c.value} value={c.value}>
                            {c.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <p className="text-xs text-muted-foreground">Sets the currency for prices and the stock sheet.</p>
                  </div>
                  {error ? (
                    <p role="alert" className="text-sm text-destructive">
                      {error}
                    </p>
                  ) : null}
                  <Button type="submit" size="lg" disabled={busy}>
                    {busy ? "Saving..." : "Continue"}
                  </Button>
                </form>
              </CardContent>
            </>
          ) : null}
          {step === "items" ? (
            <ItemsStep
              checked={checked}
              setChecked={setChecked}
              busy={busy}
              progress={progress}
              titleRef={titleRef}
              onAdd={() => void addSelected()}
              onLink={(to) => void navigate(to)}
              onSkip={() => setStep("done")}
            />
          ) : null}
          {step === "done" ? (
            <>
              <CardHeader>
                <CardTitle ref={titleRef} tabIndex={-1} className="outline-none">
                  {name.trim()} is ready
                </CardTitle>
                <CardDescription>{doneText(added, existing && existing.length)}</CardDescription>
              </CardHeader>
              <CardContent>
                <Button size="lg" className="w-full" onClick={() => void navigate("/stock", { replace: true })}>
                  Go to Stock
                </Button>
              </CardContent>
            </>
          ) : null}
        </Card>
      </div>
    </main>
  );
}
