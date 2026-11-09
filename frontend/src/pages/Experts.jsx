import Navbar from "../components/Navbar/Navbar";
import ExpertCards from "../components/ExpertCards/ExpertCards";

function Experts() {
  return (
    <>
      <Navbar />
      <div className="min-h-screen bg-slate-50">
        <ExpertCards />
      </div>
    </>
  );
}

export default Experts;