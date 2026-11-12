import { useState } from 'react';
import SignIn from './SignIn';
import Dashboard from './Dashboard';
import LockScreen from './LockScreen';
import useIdleLock from './useIdleLock';
import { createPasswordVerifier, verifyPassword } from './lib/passwordVerifier';

const IDLE_TIMEOUT_MS = 5 * 60 * 1000;
// const IDLE_TIMEOUT_MS = 5 * 1000;

const AUTH_SESSION_KEY = 'iomt-analysis-auth-session';
const LOCK_KEY = 'iomt-analysis-ui-locked';
const VERIFIER_KEY = 'iomt-analysis-unlock-verifier';

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

// Salted hash of the sign-in password, stored next to the session (never the
// password itself) so the lock screen can still verify it after a reload.
const readVerifier = () => {
  for (const storage of [window.localStorage, window.sessionStorage]) {
    try {
      const raw = storage.getItem(VERIFIER_KEY);
      if (raw) return JSON.parse(raw);
    } catch {
      // Ignore unreadable storage or corrupt JSON and treat it as missing.
    }
  }
  return null;
};

const clearAuthStorage = () => {
  for (const storage of [window.localStorage, window.sessionStorage]) {
    storage.removeItem(AUTH_SESSION_KEY);
    storage.removeItem(VERIFIER_KEY);
  }
  writeLocked(false);
};

// A reload while locked stays locked if there is a verifier to check the
// password against; otherwise the session cannot be unlocked safely, so it ends.
const restoreSession = () => {
  const user = restoreUser();
  if (user && readLocked() && !readVerifier()) {
    clearAuthStorage();
    return { user: null, locked: false };
  }
  return { user, locked: Boolean(user) && readLocked() };
};

function App() {
  const [initialSession] = useState(restoreSession);
  const [currentUser, setCurrentUser] = useState(initialSession.user);
  const [isLocked, setIsLockedState] = useState(initialSession.locked);

  const setIsLocked = (locked) => {
    writeLocked(locked);
    setIsLockedState(locked);
  };

  const handleSignOut = () => {
    clearAuthStorage();
    setIsLockedState(false);
    setCurrentUser(null);
  };

  useIdleLock({
    timeoutMs: IDLE_TIMEOUT_MS,
    enabled: Boolean(currentUser) && !isLocked,
    // Without a verifier the lock screen could never check the password.
    onIdle: () => (readVerifier() ? setIsLocked(true) : handleSignOut()),
  });

  // TODO: Integrate with backend API
  const handleSignIn = async (credentials, rememberMe) => {
    const user = {
      id: credentials.email || '12345',
      role: 'Clinical IoMT Specialist',
    };
    const storage = rememberMe ? window.localStorage : window.sessionStorage;

    let verifier = null;
    try {
      verifier = await createPasswordVerifier(credentials.password);
    } catch (error) {
      console.error('Could not create the unlock verifier; the session cannot be locked.', error);
    }

    clearAuthStorage();
    storage.setItem(AUTH_SESSION_KEY, JSON.stringify({ user }));
    if (verifier) storage.setItem(VERIFIER_KEY, JSON.stringify(verifier));
    setIsLocked(false);
    setCurrentUser(user);
  };
  // TODO: Verify the password with the backend instead of the stored verifier
  const handleUnlock = async (password) => {
    if (!(await verifyPassword(password, readVerifier()))) return false;
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
