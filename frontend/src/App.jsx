import { useRef, useState } from 'react';
import SignIn from './SignIn';
import Dashboard from './Dashboard';
import LockScreen from './LockScreen';
import useIdleLock from './useIdleLock';

const IDLE_TIMEOUT_MS = 5 * 60 * 1000;
//const IDLE_TIMEOUT_MS = 10 * 1000;

function App() {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [isLocked, setIsLocked] = useState(false);
  const [currentUser, setCurrentUser] = useState(null);
  // Kept in memory only so the lock screen can re-check it.
  const passwordRef = useRef('');

  useIdleLock({
    timeoutMs: IDLE_TIMEOUT_MS,
    enabled: isAuthenticated && !isLocked,
    onIdle: () => setIsLocked(true),
  });

  // TODO: Integrate with backend API
  const handleSignIn = (credentials) => {
    passwordRef.current = credentials.password;
    setIsAuthenticated(true);
    setCurrentUser({
      id: credentials.email || '12345',
      role: 'Clinical IoMT Specialist',
    });
  };
  const handleSignOut = () => {
    passwordRef.current = '';
    setIsLocked(false);
    setIsAuthenticated(false);
    setCurrentUser(null);
  };
  // TODO: Verify the password with the backend instead of the sign-in value
  const handleUnlock = (password) => {
    if (password !== passwordRef.current) return false;
    setIsLocked(false);
    return true;
  };
  // TODO: Use backend API for signin and signout
  return (
    <>
      {!isAuthenticated ? (
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
