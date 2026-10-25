import Dashboard from "@/components/Dashboard";

export default function Home() {
  return (
    <main className="mx-auto flex min-h-screen max-w-7xl flex-col gap-4 px-4 py-5 sm:px-6">
      <header>
        <h1 className="text-xl font-semibold tracking-tight text-slate-900">ProofLoop</h1>
        <p className="text-sm text-slate-500">
          Hurricane Isaias · Dixie and Taylor counties, Florida · plans attacked until they hold
        </p>
      </header>
      <Dashboard />
    </main>
  );
}
