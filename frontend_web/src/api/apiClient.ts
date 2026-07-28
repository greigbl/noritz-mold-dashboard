import axios from 'axios';

import { getApiUrl } from '@/lib/url-utils';

const baseApiUrl = getApiUrl();

const apiClient = axios.create({
  baseURL: baseApiUrl,
  headers: {
    Accept: 'application/json',
    'Content-type': 'application/json',
  },
  withCredentials: true,
});

apiClient.interceptors.request.use(config => {
  if (typeof FormData !== 'undefined' && config.data instanceof FormData) {
    // Let the browser set multipart boundary; default JSON content-type breaks uploads.
    if (config.headers) {
      delete config.headers['Content-Type'];
      delete config.headers['Content-type'];
    }
  }
  return config;
});

export default apiClient;
