import { useState } from 'react';
import PasswordInput from './components/PasswordInput';
import './SignIn.css';

// Shown on top of the dashboard after the idle timeout. The dashboard stays
// mounted underneath so running collections keep going.
const MAX_FAILED_ATTEMPTS = 3;

const LockScreen = ({ user, onUnlock, onSignOut }) => {
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [failedAttempts, setFailedAttempts] = useState(0);

  const handleSubmit = (e) => {
    e.preventDefault();
    if (onUnlock(password)) return;

    const attempts = failedAttempts + 1;
    if (attempts >= MAX_FAILED_ATTEMPTS) {
      onSignOut();
      return;
    }
    const remaining = MAX_FAILED_ATTEMPTS - attempts;
    setFailedAttempts(attempts);
    setError(
      `Incorrect password. ${remaining} ${remaining === 1 ? 'attempt' : 'attempts'} left before you are signed out.`,
    );
    setPassword('');
  };

  return (
    <div className="lock-overlay" role="dialog" aria-modal="true" aria-labelledby="lock-title">
      <div className="lock-card">
        <div className="logo-circle lock-logo">GE</div>
        <h2 id="lock-title">Session locked</h2>
        <p className="lock-text">
          Locked after 5 minutes of inactivity. Any diagnostic collection in progress is still
          running. Enter your password to continue as <strong>{user?.id || 'your account'}</strong>.
        </p>

        {error && (
          <div className="eds-alert-error" role="alert">
            {error}
          </div>
        )}

        <form className="signin-form-light" onSubmit={handleSubmit}>
          <div className="form-group-light">
            <label htmlFor="unlock-password">Password</label>
            <PasswordInput
              id="unlock-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="********"
              autoComplete="current-password"
              autoFocus
              required
            />
          </div>
          <button type="submit" className="signin-button-light">Unlock</button>
          <button type="button" className="lock-signout" onClick={onSignOut}>
            Sign out instead
          </button>
        </form>
      </div>
    </div>
  );
};

export default LockScreen;
