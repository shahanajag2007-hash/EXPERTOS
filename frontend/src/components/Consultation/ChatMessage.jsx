function ChatMessage({ chat }) {

  const isExpert = chat.sender === "expert";

  if (chat.type === "system") {

    return (

      <div className="flex justify-center">

        <div className="text-sm text-gray-500 bg-gray-100 px-5 py-2 rounded-full">

          {chat.message}

        </div>

      </div>

    );

  }

  return (

    <div
      className={`flex ${
        isExpert ? "justify-start" : "justify-end"
      }`}
    >

      <div
        className={`max-w-[75%] px-5 py-4 rounded-3xl shadow ${
          isExpert
            ? "bg-indigo-600 text-white rounded-tl-md"
            : "bg-green-500 text-white rounded-tr-md"
        }`}
      >

        <p className="font-semibold mb-2">

          {isExpert
            ? `${chat.expert?.emoji || "👨‍💻"} ${chat.expert?.name || "Expert"}`
            : "👤 You"}

        </p>

        <p className="leading-7 whitespace-pre-wrap">

          {chat.message}

        </p>

      </div>

    </div>

  );

}

export default ChatMessage;