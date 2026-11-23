import React from 'react';

export default function CloudLogo({ className = 'w-6 h-6' }) {
  return (
    <svg viewBox="0 0 64 64" className={className} role="img" aria-label="RamanCloud logo">
      <defs>
        <linearGradient id="cloudBody" x1="12" y1="12" x2="52" y2="54" gradientUnits="userSpaceOnUse">
          <stop stopColor="#ffffff" />
          <stop offset="0.52" stopColor="#eaf4ff" />
          <stop offset="1" stopColor="#c7e3ff" />
        </linearGradient>
        <linearGradient id="cloudAccent" x1="19" y1="16" x2="48" y2="47" gradientUnits="userSpaceOnUse">
          <stop stopColor="#47c7ff" />
          <stop offset="1" stopColor="#0071e3" />
        </linearGradient>
      </defs>
      <path
        d="M20.5 47.5C12.9 47.5 7 42.2 7 35.6c0-5.9 4.8-10.8 11.1-11.7C20.7 16.8 27.4 12 35 12c8.8 0 16.1 6.3 17.2 14.5C58 28 62 32.4 62 37.8c0 5.4-4.9 9.7-10.9 9.7H20.5Z"
        fill="url(#cloudBody)"
        stroke="rgba(0,113,227,0.28)"
        strokeWidth="2"
      />
      <path
        d="M21 37.7c5.1-7.8 11.6-10.9 19.6-9.3M34.2 23.4l6.6 5-6.6 5"
        fill="none"
        stroke="url(#cloudAccent)"
        strokeWidth="3.2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
