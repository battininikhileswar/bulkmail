import React from 'react';
import { Button } from '@/components/ui/button';
import { Mail, ShieldCheck, AlertCircle, ArrowLeft } from 'lucide-react';

export function LoginPage({ API = 'http://localhost:8000/api', error = null, onBackToLanding }) {
  const handleGoogleLogin = () => {
    window.location.href = `${API}/auth/login`;
  };

  return (
    <div
      className="min-h-screen w-full flex flex-col items-center justify-center bg-[#0A0A0A] p-4 text-[#F5F1E6] relative select-none overflow-hidden"
      style={{
        backgroundImage: 'radial-gradient(circle at 50% 40%, rgba(212,175,55,0.08) 0%, transparent 65%)',
      }}
    >
      {/* Background Glow Orb */}
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[500px] h-[500px] rounded-full bg-[radial-gradient(circle,rgba(212,175,55,0.16)_0%,rgba(212,175,55,0)_70%)] blur-[90px] pointer-events-none animate-drift-1 -z-10" />

      {/* Back to Home Button */}
      {onBackToLanding && (
        <button
          type="button"
          onClick={onBackToLanding}
          className="absolute top-6 left-6 inline-flex items-center gap-1.5 text-xs text-[#A59F8F] hover:text-[#F2D675] transition-colors"
        >
          <ArrowLeft className="w-3.5 h-3.5" />
          Back to Overview
        </button>
      )}

      <div className="w-full max-w-sm glass p-8 text-center relative z-10">
        {/* App Icon & Name */}
        <div className="w-12 h-12 bg-[linear-gradient(135deg,#F2D675_0%,#D4AF37_50%,#B8962E_100%)] rounded-xl flex items-center justify-center text-[#0A0A0A] mx-auto mb-4 shadow-[0_0_15px_rgba(212,175,55,0.4)]">
          <Mail className="w-6 h-6" />
        </div>
        <h1 className="text-xl font-bold text-[#F2D675]">Mail Assistant</h1>
        <p className="text-xs text-[#A59F8F] mt-1 mb-6 leading-relaxed">
          Sign in with your Google account to access your workspace.
        </p>

        {/* Error notification if OAuth redirect returned with error */}
        {error && (
          <div className="mb-5 p-3 rounded-lg bg-[#FF5C5C]/10 border border-[#FF5C5C]/30 text-[#FF5C5C] text-xs flex items-start gap-2 text-left">
            <AlertCircle className="w-4 h-4 text-[#FF5C5C] flex-shrink-0 mt-0.5" />
            <div>
              <p className="font-semibold">Sign In Failed</p>
              <p className="text-[11px] text-[#FF5C5C]/80 mt-0.5">{error}</p>
            </div>
          </div>
        )}

        {/* Single Google Sign-In Button */}
        <Button
          type="button"
          variant="primary"
          size="lg"
          onClick={handleGoogleLogin}
          className="w-full py-2.5 text-xs sm:text-sm font-semibold flex items-center justify-center gap-2.5 shadow-[0_0_16px_rgba(212,175,55,0.4)]"
        >
          {/* Official Google 'G' Icon */}
          <svg className="w-4 h-4" viewBox="0 0 24 24">
            <path
              fill="#0A0A0A"
              d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
            />
            <path
              fill="#0A0A0A"
              d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
            />
            <path
              fill="#0A0A0A"
              d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z"
            />
            <path
              fill="#0A0A0A"
              d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z"
            />
          </svg>
          <span>Sign in with Google</span>
        </Button>

        {/* Permissions Line */}
        <div className="mt-6 pt-5 border-t border-[rgba(212,175,55,0.18)] flex items-center justify-center gap-1.5 text-[11px] text-[#A59F8F]">
          <ShieldCheck className="w-3.5 h-3.5 text-[#D4AF37] flex-shrink-0" />
          <span>Permissions used: send email campaigns and read incoming replies.</span>
        </div>
      </div>
    </div>
  );
}
