FROM nanome/plugin-env

ENV ARGS=''
WORKDIR /app

ARG CACHEBUST

COPY environment.yml .
# COPY nanome-sdk nanome-sdk
RUN conda env update

COPY nanome-sdk nanome-sdk
RUN pip install -e nanome-sdk

# Add conda bin to PATH 
ENV PATH=/opt/conda/bin/:$PATH

COPY . .

CMD python run.py ${ARGS}
