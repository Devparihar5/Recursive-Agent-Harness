import type { HTMLAttributes } from 'react';
import { clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';
export function Badge({className,children,...props}:HTMLAttributes<HTMLSpanElement>){return <span className={twMerge(clsx('badge',String(children).match(/completed|success|accepted|valid/)&&'good',className))} {...props}>{children}</span>}
