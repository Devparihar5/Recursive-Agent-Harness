import type { ReactNode, HTMLAttributes } from 'react';
import { clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';
export function Card({className,...props}:HTMLAttributes<HTMLElement>){return <section className={twMerge(clsx('panel',className))} {...props}/>}
export function CardHeader({className,...props}:HTMLAttributes<HTMLDivElement>){return <div className={twMerge(clsx('panel-head',className))} {...props}/>}
export function Panel({title,children,aside}:{title:string,children:ReactNode,aside?:ReactNode}){return <Card><CardHeader><h2>{title}</h2>{aside}</CardHeader>{children}</Card>}
