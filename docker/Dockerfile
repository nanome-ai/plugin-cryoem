FROM continuumio/miniconda3:4.12.0

ENV ARGS=''
WORKDIR /app

ARG CACHEBUST

COPY environment.yml .
RUN conda env update

COPY . .

CMD python run.py ${ARGS}
