import { useState } from 'react';
import SignIn from './SignIn';
import Dashboard from './Dashboard';

const AUTH_SESSION_KEY = 'iomt-analysis-auth-session';

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

function App() {
  const [currentUser, setCurrentUser] = useState(restoreUser);
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
    setCurrentUser(user);
  };
  const handleSignOut = () => {
    window.localStorage.removeItem(AUTH_SESSION_KEY);
    window.sessionStorage.removeItem(AUTH_SESSION_KEY);
    setCurrentUser(null);
  };
  // TODO: Use backend API for signin and signout
  return (
    <>
      {!currentUser ? (
        <SignIn onSignIn={handleSignIn} />
      ) : (
        <Dashboard user={currentUser} onSignOut={handleSignOut} />
      )}
    </>
  );
}

export default App;
