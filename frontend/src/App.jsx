import { useRef, useState } from 'react';
import SignIn from './SignIn';
import Dashboard from './Dashboard';
import LockScreen from './LockScreen';
import useIdleLock from './useIdleLock';

const IDLE_TIMEOUT_MS = 5 * 60 * 1000;
//const IDLE_TIMEOUT_MS = 10 * 1000;

const AUTH_SESSION_KEY = 'iomt-analysis-auth-session';
const LOCK_KEY = 'iomt-analysis-ui-locked';

const restoreUser = () => {
  for (const storage of [window.localStorage, window.sessionStorage]) {
    const serializedSession = storage.getItem(AUTH_SESSION_KEY);
    if (!serializedSession) continue;

    try {
      const session = JSON.parse(serializedSession);
      if (
        typeof session?.user?.id === 'string'
        && typeof session?.user?.role === 'string'
      ) {
        return session.user;
      }
    } catch (error) {
      console.error('Could not restore the saved sign-in session.', error);
    }

    storage.removeItem(AUTH_SESSION_KEY);
  }

  return null;
};

// A page reload must not unlock the UI, so the lock flag survives in sessionStorage.
const readLocked = () => {
  try {
    return window.sessionStorage.getItem(LOCK_KEY) === '1';
  } catch {
    return false;
  }
};

const writeLocked = (locked) => {
  try {
    if (locked) window.sessionStorage.setItem(LOCK_KEY, '1');
    else window.sessionStorage.removeItem(LOCK_KEY);
  } catch {
    // Storage unavailable: the lock still works, it just won't survive a reload.
  }
};

function App() {
  const [currentUser, setCurrentUser] = useState(restoreUser);
  const [isLocked, setIsLockedState] = useState(readLocked);
  // Kept in memory only so the lock screen can re-check it. It is empty after a
  // reload with "Remember me", because the password is never saved to storage.
  const passwordRef = useRef('');

  const setIsLocked = (locked) => {
    writeLocked(locked);
    setIsLockedState(locked);
  };

  useIdleLock({
    timeoutMs: IDLE_TIMEOUT_MS,
    enabled: Boolean(currentUser) && !isLocked,
    onIdle: () => setIsLocked(true),
  });

  // TODO: Integrate with backend API
  const handleSignIn = (credentials, rememberMe) => {
    const user = {
      id: credentials.email || '12345',
      role: 'Clinical IoMT Specialist',
    };
    const storage = rememberMe ? window.localStorage : window.sessionStorage;
    const otherStorage = rememberMe ? window.sessionStorage : window.localStorage;

    storage.setItem(AUTH_SESSION_KEY, JSON.stringify({ user }));
    otherStorage.removeItem(AUTH_SESSION_KEY);
    passwordRef.current = credentials.password;
    setIsLocked(false);
    setCurrentUser(user);
  };
  const handleSignOut = () => {
    window.localStorage.removeItem(AUTH_SESSION_KEY);
    window.sessionStorage.removeItem(AUTH_SESSION_KEY);
    passwordRef.current = '';
    setIsLocked(false);
    setCurrentUser(null);
  };
  // TODO: Verify the password with the backend instead of the sign-in value
  const handleUnlock = (password) => {
    // After a reload there is no remembered password to compare with, so fall
    // back to the same non-empty check that sign-in uses today.
    const matches = passwordRef.current
      ? password === passwordRef.current
      : password.trim() !== '';
    if (!matches) return false;
    setIsLocked(false);
    return true;
  };
  // TODO: Use backend API for signin and signout
  return (
    <>
      {!currentUser ? (
        <SignIn onSignIn={handleSignIn} />
      ) : (
        <>
          {/* Stays mounted while locked so in-progress collection keeps running. */}
          <div inert={isLocked} aria-hidden={isLocked}>
            <Dashboard user={currentUser} onSignOut={handleSignOut} />
          </div>
          {isLocked && (
            <LockScreen user={currentUser} onUnlock={handleUnlock} onSignOut={handleSignOut} />
          )}
        </>
      )}
    </>
  );
}

export default App;
