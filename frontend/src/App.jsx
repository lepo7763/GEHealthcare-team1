import { useState } from 'react';
import SignIn from './SignIn';
import Dashboard from './Dashboard';

function App() {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [currentUser, setCurrentUser] = useState(null);
  // TODO: Integrate with backend API
  const handleSignIn = (credentials) => {
    setIsAuthenticated(true);
    setCurrentUser({
      id: credentials.email || '12345',
      role: 'Clinical IoMT Specialist',
    });
  };
  const handleSignOut = () => {
    setIsAuthenticated(false);
    setCurrentUser(null);
  };
  // TODO: Use backend API for signin and signout
  return (
    <>
      {!isAuthenticated ? (
        <SignIn onSignIn={handleSignIn} />
      ) : (
        <Dashboard user={currentUser} onSignOut={handleSignOut} />
      )}
    </>
  );
}

export default App;
