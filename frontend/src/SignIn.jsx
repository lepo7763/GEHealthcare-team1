import { useState } from 'react';
import './SignIn.css';

const SignIn = ({ onSignIn }) => {
  const [email, setEmail] = useState('12345');
  const [password, setPassword] = useState('12345');
  const [rememberMe, setRememberMe] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!email.trim() || !password.trim()) {
      setError('Please provide your workstation credentials.');
      return;
    }

    if (onSignIn) {
      try {
        onSignIn({ email: email.trim(), password }, rememberMe);
      } catch {
        setError('Could not save your sign-in session. Check browser storage settings and try again.');
      }
    }
  };

  return (
    <div className="signin-split-container">
      <div className="signin-left">
        <div className="left-content">
          <div className="logo-placeholder">
            {/*GE LOGO*/}
            <div className="logo-circle">GE</div>
          </div>
          <h1>IoMT Analysis Tool</h1>
          <p>
            Secure, intelligent monitoring and analytics for Internet of Medical Things (IoMT) devices.
            Empowering healthcare through data.
          </p>
        </div>
        <div className="left-background-shapes">
          <div className="shape shape-1"></div>
          <div className="shape shape-2"></div>
        </div>
      </div>

      <div className="signin-right">
        <div className="signin-card-light">
          <div className="signin-header-light">
            <h2>Sign in to your workstation</h2>
            <p>Welcome back! Use an authorized account.</p>
          </div>

          {error && (
            <div className="eds-alert-error" role="alert">
              {error}
            </div>
          )}

          <form className="signin-form-light" onSubmit={handleSubmit}>
            <div className="form-group-light">
              <label htmlFor="email">Email</label>
              <input
                type="text"
                id="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="name@gehealthcare.com"
                required
              />
            </div>

            <div className="form-group-light">
              <label htmlFor="password">Password</label>
              <input
                type="password"
                id="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="********"
                required
              />
            </div>

            <div className="form-options">
              <label className="remember-me">
                <input
                  type="checkbox"
                  checked={rememberMe}
                  onChange={(e) => setRememberMe(e.target.checked)}
                />
                <span>Remember me</span>
              </label>
              <a href="#" className="forgot-password-light">Forgot password?</a>
            </div>

            <button type="submit" className="signin-button-light">Sign In</button>
          </form>

          <div className="security-warning-card">
            <svg className="security-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
              <line x1="12" y1="9" x2="12" y2="13" />
              <line x1="12" y1="17" x2="12.01" y2="17" />
            </svg>
            <div className="security-text">
              <strong>Security Notice:</strong>Access is logged. Do not collect or enter patient identifiers. The interface locks after 5 minutes of inactivity; active backend diagnostics continue safely.
            </div>
          </div>

          <div className="signup-prompt-light">
            Cannot access your account? <a href="#">Get help</a>
          </div>
        </div>
      </div>
    </div>
  );
};

export default SignIn;
