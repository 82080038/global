"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function Home() {
  const router = useRouter();
  useEffect(() => {
    router.push("/dashboard");
  }, [router]);

  return (
    <div className="flex min-h-screen items-center justify-center bg-zinc-950 text-zinc-100">
      <p className="text-sm text-zinc-500">Opening dashboard...</p>
    </div>
  );
}
