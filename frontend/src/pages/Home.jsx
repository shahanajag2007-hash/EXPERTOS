import Navbar from "../components/Navbar/Navbar";
import Hero from "../components/Hero/Hero";
import Statistics from "../components/Statistics/Statistics";
import AIGuide from "../components/AIGuide/AIGuide";
import ExpertCards from "../components/ExpertCards/ExpertCards";
import ExpertPanel from "../components/ExpertPanel/ExpertPanel";
import Footer from "../components/Footer/Footer";
import RatingSection from "../components/Rating/RatingSection";

function Home() {
  return (
    <>
      <Navbar />
      <Hero />
      <Statistics />
      <AIGuide />
      <ExpertCards />
      <ExpertPanel />
      <RatingSection />
      <Footer />
    </>
  );
}

export default Home;