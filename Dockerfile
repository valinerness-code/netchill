FROM nginx:1.27-alpine

WORKDIR /usr/share/nginx/html

COPY . /usr/share/nginx/html
COPY default.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
