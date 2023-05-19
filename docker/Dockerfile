FROM nanome/plugin-env

ENV ARGS=''
WORKDIR /app

ARG CACHEBUST

COPY environment.yml .
RUN conda env update

COPY nanome-sdk nanome-sdk
RUN pip install -e nanome-sdk

COPY . .

CMD python run.py ${ARGS}
