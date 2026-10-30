import { forwardRef } from 'react';
import type { ButtonHTMLAttributes } from 'react';
import { clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';
export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement>{secondary?:boolean}
export const Button=forwardRef<HTMLButtonElement,ButtonProps>(({className,secondary=false,type='button',...props},ref)=><button ref={ref} type={type} className={twMerge(clsx('button',secondary&&'secondary',className))} {...props}/>);
Button.displayName='Button';
