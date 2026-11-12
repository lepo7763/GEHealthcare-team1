import { Dialog as DialogPrimitive } from 'radix-ui';
import { cn } from '@/lib/utils';

function Dialog(props) {
  return <DialogPrimitive.Root data-slot="dialog" {...props} />;
}

function DialogContent({ className, children, ...props }) {
  return (
    <DialogPrimitive.Portal>
      <DialogPrimitive.Overlay data-slot="dialog-overlay" className="dialog-overlay" />
      <DialogPrimitive.Content
        data-slot="dialog-content"
        className={cn('dialog-content', className)}
        {...props}
      >
        {children}
      </DialogPrimitive.Content>
    </DialogPrimitive.Portal>
  );
}

function DialogTitle({ className, ...props }) {
  return <DialogPrimitive.Title className={cn('dialog-title', className)} {...props} />;
}

function DialogDescription({ className, ...props }) {
  return (
    <DialogPrimitive.Description className={cn('dialog-description', className)} {...props} />
  );
}

export { Dialog, DialogContent, DialogTitle, DialogDescription };
