# Final Output Storage

This directory is reserved for immutable delivery assets produced by the MAS video workflow. The backend automatically moves composed videos (with background music and voice-over) here, marks them read-only, and pushes a copy to OSS for durability. Do not place temporary files in this folder; intermediate artifacts should continue to use `storage/temp` or `storage/generated`.
