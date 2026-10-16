import { useEffect, useRef } from 'react';

const ACTIVITY_EVENTS = ['mousemove', 'mousedown', 'keydown', 'wheel', 'touchstart', 'scroll'];

// Calls onIdle once the user has had no mouse/keyboard/touch activity for
// timeoutMs. Only the UI is affected: nothing here touches backend work.
// Pass enabled=false (e.g. while locked or signed out) to stop watching.
const useIdleLock = ({ timeoutMs, enabled, onIdle }) => {
  const lastActivity = useRef(0);
  const onIdleRef = useRef(onIdle);

  useEffect(() => {
    onIdleRef.current = onIdle;
  }, [onIdle]);

  useEffect(() => {
    if (!enabled) return undefined;

    lastActivity.current = Date.now();
    const markActive = () => {
      lastActivity.current = Date.now();
    };
    // Capture phase so scroll events (which don't bubble) are seen too.
    ACTIVITY_EVENTS.forEach((name) =>
      window.addEventListener(name, markActive, { passive: true, capture: true }),
    );

    // Compare timestamps instead of one long timeout so a sleeping laptop
    // locks as soon as it wakes up.
    const timer = setInterval(() => {
      if (Date.now() - lastActivity.current >= timeoutMs) {
        onIdleRef.current();
      }
    }, 1000);

    return () => {
      clearInterval(timer);
      ACTIVITY_EVENTS.forEach((name) =>
        window.removeEventListener(name, markActive, { capture: true }),
      );
    };
  }, [enabled, timeoutMs]);
};

export default useIdleLock;
