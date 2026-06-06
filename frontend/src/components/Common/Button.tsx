import React from 'react';

type Variant = 'primary' | 'secondary' | 'danger' | 'ghost';

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  loading?: boolean;
}

const variants: Record<Variant, string> = {
  primary: 'bg-deloitte-green text-white hover:opacity-90',
  secondary: 'bg-black text-white hover:opacity-90',
  danger: 'bg-error text-white hover:opacity-90',
  ghost: 'bg-gray-100 text-gray-900 hover:bg-gray-200',
};

export const Button: React.FC<ButtonProps> = ({
  variant = 'primary',
  loading,
  className = '',
  children,
  disabled,
  ...props
}) => (
  <button
    type="button"
    className={`px-4 py-2 rounded-lg font-medium transition-opacity disabled:opacity-50 ${variants[variant]} ${className}`}
    disabled={disabled || loading}
    {...props}
  >
    {loading ? 'Loading…' : children}
  </button>
);
