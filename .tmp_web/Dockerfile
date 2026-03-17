FROM node:20-slim

WORKDIR /app

COPY package*.json ./
RUN npm install

COPY . .

ENV NEXT_TELEMETRY_DISABLED 1
ENV NODE_ENV development

CMD ["npm", "run", "dev"]
