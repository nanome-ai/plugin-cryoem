FROM nanome/plugin-env

ENV ARGS=''
WORKDIR /app

ARG CACHEBUST

COPY environment.yml .
RUN conda env update

COPY . .

CMD python run.py ${ARGS}
