import React from 'react';

export default function CloudLogo({ className = 'w-6 h-6' }) {
  return (
    <img src={`${import.meta.env.BASE_URL}logo-v1.png`} alt="RamanCloud logo" className={`${className} object-contain`} />
  );
}
