import { useState } from "react";
import type { FormEvent } from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { AccountImportFileResult } from "@/features/accounts/hooks/use-accounts";

export type ImportDialogProps = {
  open: boolean;
  busy: boolean;
  onOpenChange: (open: boolean) => void;
  onImport: (files: File[]) => Promise<AccountImportFileResult[]>;
};

export function ImportDialog({
  open,
  busy,
  onOpenChange,
  onImport,
}: ImportDialogProps) {
  const [files, setFiles] = useState<File[]>([]);
  const [failures, setFailures] = useState<AccountImportFileResult[]>([]);
  const [inputKey, setInputKey] = useState(0);
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (files.length === 0) {
      return;
    }

    setSubmitting(true);
    try {
      const results = await onImport(files);
      const failed = results.filter((result) => result.error !== null);
      setFailures(failed);
      setFiles(failed.map((result) => result.file));
      setInputKey((currentKey) => currentKey + 1);
      if (failed.length === 0) {
        onOpenChange(false);
      }
    } finally {
      setSubmitting(false);
    }
  };

  const importBusy = busy || submitting;

  return (
    <Dialog
      open={open}
      onOpenChange={(nextOpen) => {
        if (!importBusy) onOpenChange(nextOpen);
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Import auth.json</DialogTitle>
          <DialogDescription>Upload one or more exported account auth.json files.</DialogDescription>
        </DialogHeader>

        <form className="space-y-4" aria-busy={importBusy} onSubmit={handleSubmit}>
          <div className="space-y-2">
            <Label htmlFor="auth-json-file">Files</Label>
            <Input
              key={inputKey}
              id="auth-json-file"
              type="file"
              accept="application/json,.json"
              multiple
              disabled={importBusy}
              onChange={(event) => {
                setFiles(Array.from(event.currentTarget.files ?? []));
                setFailures([]);
              }}
            />
          </div>

          {files.length > 0 ? (
            <div className="space-y-1 text-xs text-muted-foreground">
              <p>Selected files</p>
              <ul className="max-h-28 space-y-1 overflow-y-auto rounded-md border px-2 py-1">
                {files.map((file, index) => (
                  <li
                    key={`${file.name}-${file.size}-${file.lastModified}-${index}`}
                    className="truncate"
                    title={file.name}
                  >
                    {file.name}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          {failures.length > 0 ? (
            <ul
              role="alert"
              className="max-h-28 space-y-1 overflow-y-auto rounded-md border border-destructive/30 bg-destructive/10 px-2 py-1 text-xs text-destructive"
            >
              {failures.map((failure, index) => (
                <li key={`${failure.file.name}-${index}`}>
                  {failure.file.name}: {failure.error}
                </li>
              ))}
            </ul>
          ) : null}

          <DialogFooter>
            <Button type="submit" disabled={importBusy || files.length === 0}>
              Import
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
