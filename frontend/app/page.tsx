"use client";
import { useEffect } from "react";

export default function Index() {
  useEffect(() => {
    window.location.replace("/occ/");
  }, []);
  return <div className="h-full grid place-items-center text-dim text-sm">Opening the Operations Command Centre…</div>;
}
