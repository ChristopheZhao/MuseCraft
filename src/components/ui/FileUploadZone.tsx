'use client';

import React, { useCallback } from 'react';
import { useDropzone } from 'react-dropzone';
import { Upload, X, File, Image as ImageIcon, Video, FileText } from 'lucide-react';
import { cn, formatFileSize, getFileType } from '@/lib/utils';
import { useI18n } from '@/i18n/I18nProvider';

interface FileUploadZoneProps {
  onFilesSelected: (files: File[]) => void;
  acceptedTypes: string[];
  maxFiles?: number;
  maxSize?: number;
  className?: string;
}

const FileUploadZone: React.FC<FileUploadZoneProps> = ({
  onFilesSelected,
  acceptedTypes,
  maxFiles = 5,
  maxSize = 10 * 1024 * 1024, // 10MB default
  className,
}) => {
  const [selectedFiles, setSelectedFiles] = React.useState<File[]>([]);
  const { t } = useI18n();

  const onDrop = useCallback((acceptedFiles: File[]) => {
    const newFiles = [...selectedFiles, ...acceptedFiles].slice(0, maxFiles);
    setSelectedFiles(newFiles);
    onFilesSelected(newFiles);
  }, [selectedFiles, maxFiles, onFilesSelected]);

  const removeFile = (index: number) => {
    const newFiles = selectedFiles.filter((_, i) => i !== index);
    setSelectedFiles(newFiles);
    onFilesSelected(newFiles);
  };

  const { getRootProps, getInputProps, isDragActive, fileRejections } = useDropzone({
    onDrop,
    accept: acceptedTypes.reduce((acc, type) => ({ ...acc, [type]: [] }), {}),
    maxSize,
    maxFiles: maxFiles - selectedFiles.length,
  });

  const getFileIcon = (file: File) => {
    const type = getFileType(file);
    switch (type) {
      case 'image':
        return <ImageIcon className="w-8 h-8 text-green-500" />;
      case 'video':
        return <Video className="w-8 h-8 text-blue-500" />;
      case 'document':
        return <FileText className="w-8 h-8 text-orange-500" />;
      default:
        return <File className="w-8 h-8 text-gray-500" />;
    }
  };

  return (
    <div className={cn("space-y-4", className)}>
      {/* Drop Zone */}
      <div
        {...getRootProps()}
        className={cn(
          "border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-colors",
          isDragActive
            ? "border-primary-500 bg-primary-50"
            : "border-gray-300 hover:border-gray-400 bg-gray-50"
        )}
      >
        <input {...getInputProps()} />
        <Upload className="w-12 h-12 text-gray-400 mx-auto mb-4" />
        
        {isDragActive ? (
          <p className="text-primary-600 font-medium">
            {t('upload.dropHere')}
          </p>
        ) : (
          <div>
            <p className="text-gray-600 font-medium mb-2">
              {t('upload.dragDrop')}
            </p>
            <p className="text-sm text-gray-500">
              {t('upload.supports.prefix')}{formatFileSize(maxSize)}{t('upload.supports.suffix')}
            </p>
          </div>
        )}
      </div>

      {/* File Rejections */}
      {fileRejections.length > 0 && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-3">
          <h4 className="text-sm font-medium text-red-800 mb-2">
            {t('upload.rejected')}
          </h4>
          <ul className="text-sm text-red-700 space-y-1">
            {fileRejections.map(({ file, errors }) => (
              <li key={file.name}>
                {file.name}: {errors.map(e => e.message).join(', ')}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Selected Files */}
      {selectedFiles.length > 0 && (
        <div className="space-y-2">
          <h4 className="text-sm font-medium text-gray-700">
            {t('upload.selectedFiles')} ({selectedFiles.length}/{maxFiles})
          </h4>
          <div className="space-y-2">
            {selectedFiles.map((file, index) => (
              <div
                key={`${file.name}-${index}`}
                className="flex items-center space-x-3 p-3 bg-white border border-gray-200 rounded-lg"
              >
                {getFileIcon(file)}
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-gray-900 truncate">
                    {file.name}
                  </p>
                  <p className="text-xs text-gray-500">
                    {formatFileSize(file.size)} • {getFileType(file)}
                  </p>
                </div>
                <button
                  onClick={() => removeFile(index)}
                  className="p-1 text-gray-400 hover:text-red-500 transition-colors"
                  aria-label={`${t('upload.remove')} ${file.name}`}
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Upload Limits Info */}
      <div className="text-xs text-gray-500 space-y-1">
        <p>
          • 最多 {maxFiles} 个文件，每个不超过 {formatFileSize(maxSize)}
        </p>
        <p>
          {t('upload.formats')}
        </p>
      </div>
    </div>
  );
};

export default FileUploadZone;
