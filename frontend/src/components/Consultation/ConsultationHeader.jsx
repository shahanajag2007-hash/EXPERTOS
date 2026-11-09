function ConsultationHeader({ expert }) {

  if (!expert) return null;

  return (

    <div className="bg-gradient-to-r from-indigo-600 via-indigo-700 to-purple-700 rounded-3xl p-6 sm:p-10 text-white shadow-xl">

      <div className="flex flex-col md:flex-row justify-between items-start gap-6">

        <div className="flex flex-col sm:flex-row gap-6">

          <div className="w-20 h-20 sm:w-24 sm:h-24 shrink-0 rounded-full bg-white/20 flex items-center justify-center text-5xl">

            {expert.emoji}

          </div>

          <div>

            <h1 className="text-3xl sm:text-4xl font-bold">

              {expert.name}

            </h1>

            <p className="text-indigo-100 mt-2 text-lg">

              {expert.role}

            </p>

            <div className="flex items-center gap-2 mt-5">

              <span className="w-3 h-3 bg-green-400 rounded-full"></span>

              <span>

                {expert.status}

              </span>

            </div>

            <div className="flex flex-wrap gap-3 mt-6">

              {(expert.expertise || []).map((item, index) => (

                <span

                  key={index}

                  className="bg-white/20 px-4 py-2 rounded-full text-sm"

                >

                  {item}

                </span>

              ))}

            </div>

          </div>

        </div>

        <div className="md:text-right">

          <p className="inline-block bg-white/15 px-4 py-2 rounded-full text-sm">

            AI Expert

          </p>

        </div>

      </div>

      <div className="mt-10 bg-white/10 rounded-2xl p-6">

        <p className="leading-8 text-lg">

          {expert.greeting}

        </p>

      </div>

    </div>

  );

}

export default ConsultationHeader;