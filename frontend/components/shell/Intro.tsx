"use client";
import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useState } from "react";
import { Logo } from "./TopNav";

/** Short cinematic opening (≈2 s, skippable, once per browser session). */
export default function Intro({ onDone }: { onDone: () => void }) {
  const [show, setShow] = useState(true);
  useEffect(() => {
    const t = setTimeout(() => setShow(false), 2100);
    return () => clearTimeout(t);
  }, []);
  return (
    <AnimatePresence onExitComplete={onDone}>
      {show && (
        <motion.div className="fixed inset-0 z-50 grid place-items-center bg-[#04070d]"
          initial={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.7, ease: "easeOut" }}>
          <motion.div className="flex flex-col items-center" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6 }}>
            <Logo size={58} />
            <div className="mt-5 text-[30px] font-semibold tracking-tight">SkyAssist</div>
            <div className="mt-1 text-[12px] tracking-[0.32em] text-muted uppercase">Airport Digital Twin · Agentic Operations</div>
            <motion.div className="mt-6 h-[2px] w-56 rounded bg-gradient-to-r from-cyan to-violet origin-left"
              initial={{ scaleX: 0 }} animate={{ scaleX: 1 }} transition={{ duration: 1.6, ease: "easeInOut" }} />
          </motion.div>
          <button onClick={() => setShow(false)} className="absolute bottom-8 right-8 text-[12px] text-muted hover:text-text">Skip ⏭</button>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
