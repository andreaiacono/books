/**
 * Convert a File (image) to a WebP base64 string (without the data URL prefix).
 */
export function fileToWebPBase64(file) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => {
      const canvas = document.createElement('canvas');
      canvas.width = img.width;
      canvas.height = img.height;
      canvas.getContext('2d').drawImage(img, 0, 0);
      resolve(canvas.toDataURL('image/webp', 0.85).split(',')[1]);
      URL.revokeObjectURL(img.src);
    };
    img.onerror = () => { URL.revokeObjectURL(img.src); reject(new Error('Invalid image')); };
    img.src = URL.createObjectURL(file);
  });
}

/**
 * Convert a data URL (any image format) to a WebP base64 string (without the data URL prefix).
 */
export function dataUrlToWebPBase64(dataUrl) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => {
      const canvas = document.createElement('canvas');
      canvas.width = img.width;
      canvas.height = img.height;
      canvas.getContext('2d').drawImage(img, 0, 0);
      resolve(canvas.toDataURL('image/webp', 0.82).split(',')[1]);
    };
    img.onerror = reject;
    img.src = dataUrl;
  });
}

/**
 * Read a File as a data URL string.
 */
export function readFileAsDataURL(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}
