alter table document
  add column original_filename text,
  add constraint document_original_filename_length_check
    check (original_filename is null or char_length(original_filename) between 1 and 255);

comment on column document.original_filename is
  'Original Unicode filename for display and downloads; storage_path uses an ASCII-safe leaf name.';
